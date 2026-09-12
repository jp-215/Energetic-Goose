"""Tiny JSON document store for evaluation sessions and imported personas.

Kept deliberately dependency-free: one JSON file per collection under the
data directory (EVAL_DATA_DIR, default services/court-orchestrator/var/).
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

SERVICE_DIR = Path(__file__).resolve().parent.parent.parent


def data_dir() -> Path:
    override = os.environ.get("EVAL_DATA_DIR", "").strip()
    path = Path(override) if override else SERVICE_DIR / "var"
    path.mkdir(parents=True, exist_ok=True)
    return path


class JsonCollection:
    """Ordered id -> document map persisted atomically to <name>.json."""

    def __init__(self, name: str, directory: Optional[Path] = None):
        self._name = name
        self._dir = directory
        self._lock = threading.RLock()
        self._docs: Optional[Dict[str, Dict[str, Any]]] = None

    @property
    def path(self) -> Path:
        return (self._dir or data_dir()) / f"{self._name}.json"

    def _ensure_loaded(self) -> Dict[str, Dict[str, Any]]:
        if self._docs is None:
            if self.path.exists():
                try:
                    self._docs = json.loads(self.path.read_text(encoding="utf-8"))
                except Exception:
                    self._docs = {}
            else:
                self._docs = {}
        return self._docs

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._docs, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.path)

    def all(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._ensure_loaded().values())

    def get(self, doc_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._ensure_loaded().get(doc_id)

    def put(self, doc_id: str, doc: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            self._ensure_loaded()[doc_id] = doc
            self._save()
            return doc

    def delete(self, doc_id: str) -> bool:
        with self._lock:
            docs = self._ensure_loaded()
            existed = docs.pop(doc_id, None) is not None
            if existed:
                self._save()
            return existed

    def clear(self) -> None:
        with self._lock:
            self._docs = {}
            self._save()

    def reset_cache(self) -> None:
        with self._lock:
            self._docs = None


sessions = JsonCollection("sessions")
personas = JsonCollection("personas")
