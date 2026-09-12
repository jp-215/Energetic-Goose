"""Interaction graph: how simulated persona agents use the models under test.

Schema (shared by both backends):

    (:Model {name, vendor, region})
    (:Session {id, created_at, status, final_score, benchmark_score, agent_score})
    (:Agent {id, name, role, traits})
    (:Benchmark {name, source, task_type})
    (:Feedback {id, score, ratings_json, summary, would_use_again})
    (:Turn {id, index, role, content, latency_ms})

    (Session)-[:EVALUATES]->(Model)
    (Session)-[:RAN_BENCHMARK {score, correct, total}]->(Benchmark)
    (Agent)-[:PARTICIPATED_IN]->(Session)
    (Agent)-[:INTERACTED_WITH {session_id, turns, score}]->(Model)
    (Agent)-[:SENT]->(Turn)        user turns authored by the persona
    (Model)-[:REPLIED]->(Turn)     assistant turns authored by the model
    (Turn)-[:NEXT]->(Turn)         conversation order
    (Turn)-[:IN_SESSION]->(Session)
    (Agent)-[:GAVE]->(Feedback)-[:ABOUT]->(Model)
    (Feedback)-[:IN_SESSION]->(Session)

Backends:
  * Neo4jGraphStore  — real Neo4j via bolt (NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD)
  * MemoryGraphStore — same API, in-process, persisted to var/graph.json, used
                       automatically when Neo4j is not configured/reachable
"""

from __future__ import annotations

import json
import logging
import re
import threading
from pathlib import Path
from typing import Any, Dict, Optional

from .config import get_neo4j_settings

logger = logging.getLogger("datacat")

_LABEL_RE = re.compile(r"^[A-Z][A-Za-z0-9_]*$")

# Node label -> property used as its identity in MERGE.
NODE_KEYS = {
    "Model": "name",
    "Session": "id",
    "Agent": "id",
    "Benchmark": "name",
    "Feedback": "id",
    "Turn": "id",
}


def _check_label(label: str) -> str:
    if not _LABEL_RE.match(label):
        raise ValueError(f"invalid graph label {label!r}")
    return label


def _clean(props: Dict[str, Any]) -> Dict[str, Any]:
    """Neo4j properties must be primitives/arrays of primitives."""
    out: Dict[str, Any] = {}
    for key, value in props.items():
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            out[key] = value
        elif isinstance(value, (list, tuple)) and all(
            isinstance(v, (str, int, float, bool)) for v in value
        ):
            out[key] = list(value)
        else:
            out[key] = json.dumps(value, ensure_ascii=False)
    return out


class GraphStore:
    backend = "abstract"

    def merge_node(self, label: str, props: Dict[str, Any]) -> None:
        raise NotImplementedError

    def merge_rel(
        self,
        from_label: str,
        from_key: Any,
        rel_type: str,
        to_label: str,
        to_key: Any,
        props: Optional[Dict[str, Any]] = None,
    ) -> None:
        raise NotImplementedError

    def session_subgraph(self, session_id: str) -> Dict[str, Any]:
        raise NotImplementedError

    def delete_session(self, session_id: str) -> None:
        raise NotImplementedError

    def status(self) -> Dict[str, Any]:
        raise NotImplementedError

    def run_cypher(self, query: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# In-memory fallback (persisted to disk)
# ---------------------------------------------------------------------------

class MemoryGraphStore(GraphStore):
    backend = "memory"

    def __init__(self, path: Optional[Path] = None):
        self._lock = threading.Lock()
        self._path = path
        self._nodes: Dict[str, Dict[str, Any]] = {}  # "Label:key" -> node
        self._rels: Dict[str, Dict[str, Any]] = {}  # "from|TYPE|to|session" -> rel
        self._load()

    # -- persistence -------------------------------------------------------
    def _load(self) -> None:
        if not self._path or not self._path.exists():
            return
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
            self._nodes = payload.get("nodes", {})
            self._rels = payload.get("rels", {})
        except Exception as exc:  # corrupt file: start fresh rather than crash
            logger.warning("graph: could not load %s (%s); starting empty", self._path, exc)

    def _save(self) -> None:
        if not self._path:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"nodes": self._nodes, "rels": self._rels}), encoding="utf-8")
        tmp.replace(self._path)

    # -- API ---------------------------------------------------------------
    @staticmethod
    def _nid(label: str, key: Any) -> str:
        return f"{label}:{key}"

    def merge_node(self, label: str, props: Dict[str, Any]) -> None:
        _check_label(label)
        key_prop = NODE_KEYS[label]
        nid = self._nid(label, props[key_prop])
        with self._lock:
            node = self._nodes.setdefault(nid, {"id": nid, "label": label, "properties": {}})
            node["properties"].update(_clean(props))
            self._save()

    def merge_rel(self, from_label, from_key, rel_type, to_label, to_key, props=None) -> None:
        _check_label(from_label)
        _check_label(to_label)
        _check_label(rel_type)
        props = _clean(props or {})
        src, dst = self._nid(from_label, from_key), self._nid(to_label, to_key)
        rid = f"{src}|{rel_type}|{dst}|{props.get('session_id', '')}"
        with self._lock:
            rel = self._rels.setdefault(
                rid, {"id": rid, "type": rel_type, "from": src, "to": dst, "properties": {}}
            )
            rel["properties"].update(props)
            self._save()

    def _session_node_ids(self, session_id: str) -> set:
        sid = self._nid("Session", session_id)
        ids = {sid}
        for rel in self._rels.values():
            if rel["to"] == sid or rel["from"] == sid:
                ids.add(rel["from"])
                ids.add(rel["to"])
            if rel["properties"].get("session_id") == session_id:
                ids.add(rel["from"])
                ids.add(rel["to"])
        # Turn/Feedback nodes link to the session; pull their authors too.
        for rel in list(self._rels.values()):
            if rel["from"] in ids and rel["type"] in ("ABOUT", "NEXT"):
                ids.add(rel["to"])
            if rel["to"] in ids and rel["type"] in ("SENT", "REPLIED", "GAVE"):
                ids.add(rel["from"])
        return ids

    def session_subgraph(self, session_id: str) -> Dict[str, Any]:
        with self._lock:
            ids = self._session_node_ids(session_id)
            nodes = [self._nodes[i] for i in ids if i in self._nodes]
            rels = [
                r for r in self._rels.values()
                if r["from"] in ids and r["to"] in ids
                and (not r["properties"].get("session_id")
                     or r["properties"].get("session_id") == session_id)
            ]
        return {"nodes": nodes, "relationships": rels}

    def delete_session(self, session_id: str) -> None:
        sid = self._nid("Session", session_id)
        with self._lock:
            owned = {
                n for n, node in self._nodes.items()
                if node["label"] in ("Turn", "Feedback")
                and node["properties"].get("session_id") == session_id
            } | {sid}
            for nid in owned:
                self._nodes.pop(nid, None)
            self._rels = {
                rid: r for rid, r in self._rels.items()
                if r["from"] not in owned and r["to"] not in owned
                and r["properties"].get("session_id") != session_id
            }
            self._save()

    def status(self) -> Dict[str, Any]:
        with self._lock:
            counts: Dict[str, int] = {}
            for node in self._nodes.values():
                counts[node["label"]] = counts.get(node["label"], 0) + 1
            return {
                "backend": self.backend,
                "connected": True,
                "uri": str(self._path) if self._path else "in-process",
                "nodes": len(self._nodes),
                "relationships": len(self._rels),
                "labels": counts,
            }

    def run_cypher(self, query: str, params=None) -> Dict[str, Any]:
        raise RuntimeError("Cypher queries require a Neo4j backend (set NEO4J_URI).")


# ---------------------------------------------------------------------------
# Neo4j backend
# ---------------------------------------------------------------------------

class Neo4jGraphStore(GraphStore):
    backend = "neo4j"

    def __init__(self, uri: str, user: str, password: str, database: str = "neo4j"):
        from neo4j import GraphDatabase  # imported lazily: optional dependency at runtime

        self._uri = uri
        self._database = database
        self._driver = GraphDatabase.driver(uri, auth=(user, password))
        self._driver.verify_connectivity()
        self._ensure_constraints()

    def close(self) -> None:
        self._driver.close()

    def _run(self, query: str, **params):
        with self._driver.session(database=self._database) as session:
            return session.run(query, **params).data()

    def _ensure_constraints(self) -> None:
        for label, key in NODE_KEYS.items():
            self._run(
                f"CREATE CONSTRAINT {label.lower()}_{key}_unique IF NOT EXISTS "
                f"FOR (n:{label}) REQUIRE n.{key} IS UNIQUE"
            )

    def merge_node(self, label: str, props: Dict[str, Any]) -> None:
        _check_label(label)
        key = NODE_KEYS[label]
        props = _clean(props)
        self._run(
            f"MERGE (n:{label} {{{key}: $key}}) SET n += $props",
            key=props[key],
            props=props,
        )

    def merge_rel(self, from_label, from_key, rel_type, to_label, to_key, props=None) -> None:
        _check_label(from_label)
        _check_label(to_label)
        _check_label(rel_type)
        fk, tk = NODE_KEYS[from_label], NODE_KEYS[to_label]
        props = _clean(props or {})
        if "session_id" in props:
            match = f"MERGE (a)-[r:{rel_type} {{session_id: $sid}}]->(b)"
        else:
            match = f"MERGE (a)-[r:{rel_type}]->(b)"
        self._run(
            f"MATCH (a:{from_label} {{{fk}: $fk}}), (b:{to_label} {{{tk}: $tk}}) "
            f"{match} SET r += $props",
            fk=from_key,
            tk=to_key,
            sid=props.get("session_id"),
            props=props,
        )

    SESSION_QUERY = (
        "MATCH (s:Session {id: $sid}) "
        "OPTIONAL MATCH (s)-[r1]-(n1) "
        "OPTIONAL MATCH (n1)-[r2]-(n2) "
        "WHERE (n1:Turn OR n1:Feedback OR n1:Agent) "
        "  AND (n2:Agent OR n2:Model OR n2:Turn OR n2:Feedback) "
        "  AND (r2.session_id IS NULL OR r2.session_id = $sid) "
        "  AND (n2.session_id IS NULL OR n2.session_id = $sid) "
        "WITH collect(DISTINCT s) + collect(DISTINCT n1) + collect(DISTINCT n2) AS ns, "
        "     collect(DISTINCT r1) + collect(DISTINCT r2) AS rs "
        "RETURN [n IN ns WHERE n IS NOT NULL | "
        "        {id: elementId(n), label: head(labels(n)), properties: properties(n)}] AS nodes, "
        "       [r IN rs WHERE r IS NOT NULL | "
        "        {id: elementId(r), type: type(r), from: elementId(startNode(r)), "
        "         to: elementId(endNode(r)), properties: properties(r)}] AS relationships"
    )

    def session_subgraph(self, session_id: str) -> Dict[str, Any]:
        rows = self._run(self.SESSION_QUERY, sid=session_id)
        if not rows:
            return {"nodes": [], "relationships": []}
        row = rows[0]
        return {"nodes": row["nodes"], "relationships": row["relationships"]}

    def delete_session(self, session_id: str) -> None:
        self._run(
            "MATCH (n) WHERE (n:Turn OR n:Feedback) AND n.session_id = $sid DETACH DELETE n",
            sid=session_id,
        )
        self._run("MATCH ()-[r {session_id: $sid}]-() DELETE r", sid=session_id)
        self._run("MATCH (s:Session {id: $sid}) DETACH DELETE s", sid=session_id)

    def status(self) -> Dict[str, Any]:
        try:
            labels = self._run("MATCH (n) RETURN head(labels(n)) AS label, count(*) AS c")
            rels = self._run("MATCH ()-[r]->() RETURN count(r) AS c")
            counts = {row["label"]: row["c"] for row in labels}
            return {
                "backend": self.backend,
                "connected": True,
                "uri": self._uri,
                "nodes": sum(counts.values()),
                "relationships": rels[0]["c"] if rels else 0,
                "labels": counts,
            }
        except Exception as exc:
            return {"backend": self.backend, "connected": False, "uri": self._uri, "error": str(exc)}

    _FORBIDDEN = re.compile(
        r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|CALL\s+dbms|LOAD\s+CSV)\b", re.IGNORECASE
    )

    def run_cypher(self, query: str, params=None) -> Dict[str, Any]:
        if self._FORBIDDEN.search(query):
            raise ValueError("Only read-only Cypher (MATCH/RETURN) is allowed here.")
        with self._driver.session(database=self._database) as session:
            result = session.run(query, **(params or {}))
            keys = list(result.keys())
            rows = []
            for record in result:
                rows.append([_serialize(record[k]) for k in keys])
            return {"columns": keys, "rows": rows}


def _serialize(value: Any) -> Any:
    """Convert neo4j graph types into plain JSON."""
    try:
        from neo4j.graph import Node, Path, Relationship
    except Exception:  # pragma: no cover
        return value
    if isinstance(value, Node):
        return {"id": value.element_id, "labels": list(value.labels), "properties": dict(value)}
    if isinstance(value, Relationship):
        return {
            "id": value.element_id,
            "type": value.type,
            "from": value.start_node.element_id if value.start_node else None,
            "to": value.end_node.element_id if value.end_node else None,
            "properties": dict(value),
        }
    if isinstance(value, Path):
        return {"nodes": [_serialize(n) for n in value.nodes],
                "relationships": [_serialize(r) for r in value.relationships]}
    if isinstance(value, list):
        return [_serialize(v) for v in value]
    if isinstance(value, dict):
        return {k: _serialize(v) for k, v in value.items()}
    return value


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_store: Optional[GraphStore] = None
_store_lock = threading.Lock()


def get_graph(data_dir: Optional[Path] = None) -> GraphStore:
    """Neo4j when configured and reachable, otherwise the persisted in-memory
    graph. Resolved once per process."""
    global _store
    with _store_lock:
        if _store is not None:
            return _store
        settings = get_neo4j_settings()
        if settings["uri"]:
            try:
                _store = Neo4jGraphStore(
                    settings["uri"], settings["user"], settings["password"], settings["database"]
                )
                logger.info("graph: connected to Neo4j at %s", settings["uri"])
                return _store
            except Exception as exc:
                logger.warning("graph: Neo4j unavailable (%s); using in-memory graph", exc)
        from .store import data_dir as default_data_dir

        _store = MemoryGraphStore((data_dir or default_data_dir()) / "graph.json")
        return _store


def reset_graph_for_tests(store: Optional[GraphStore] = None) -> None:
    global _store
    with _store_lock:
        _store = store
