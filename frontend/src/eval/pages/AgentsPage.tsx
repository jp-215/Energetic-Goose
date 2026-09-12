import { useEffect, useRef, useState } from 'react'
import { deletePersona, fetchPersonas, importPersonas, resetPersonas, updatePersona } from '../api'
import { ScoreBar } from '../components/ScoreTile'
import { useEvalStore } from '../store'
import { DIMENSIONS, type Persona } from '../types'

const TEMPLATE: Omit<Persona, 'id' | 'builtin'> = {
  name: 'Diego Ramirez',
  avatar: '🧑‍🍳',
  tagline: 'Small-business owner, English is his second language',
  age: 45,
  occupation: 'Owner of a family taqueria',
  language: 'en',
  background: 'Runs a busy restaurant, handles suppliers and marketing himself. Reads English well but writes it slowly, and wants help that sounds like him.',
  personality_traits: ['warm', 'practical', 'proud', 'time-poor'],
  communication_style: 'Short messages, occasional Spanish words, asks for things to be simpler when they are not.',
  expertise_level: 'novice',
  patience: 6,
  strictness: 5,
  priorities: { helpfulness: 0.3, accuracy: 0.15, clarity: 0.3, tone: 0.15, trust: 0.1 },
  scenario: {
    title: 'Firm but polite email to a late supplier',
    goal: 'Get a ready-to-send email in plain English that keeps the relationship but demands a delivery date.',
    opening_message: 'Hi, I need help to write an email to my meat supplier. He is late 2 weeks now and my customers ask for carnitas. I want to be polite but firm, and I want a date. Can you write it? Not too long.',
    success_criteria: ['Produces a complete, short email', 'Tone is firm but polite', 'Asks for or includes a concrete delivery date', 'Uses plain English'],
  },
}

export default function AgentsPage() {
  const [personas, setPersonas] = useState<Persona[]>([])
  const [editing, setEditing] = useState<Persona | null>(null)
  const [draft, setDraft] = useState('')
  const [importText, setImportText] = useState('')
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const syncStore = useEvalStore((s) => s.setPersonas)

  const apply = (list: Persona[]) => { setPersonas(list); syncStore(list) }
  useEffect(() => { fetchPersonas().then((r) => apply(r.personas)).catch((e) => setError(String(e))) }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const doImport = async (raw: string) => {
    setError(null); setMessage(null)
    try {
      const parsed = JSON.parse(raw)
      const res = await importPersonas(parsed)
      apply(res.personas)
      setMessage(`Imported ${res.imported.length} persona(s): ${res.imported.join(', ')}`)
      setImportText('')
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }
  const onFile = (file: File | undefined) => {
    if (!file) return
    const reader = new FileReader()
    reader.onload = () => void doImport(String(reader.result))
    reader.readAsText(file)
  }
  const exportAll = () => {
    const blob = new Blob([JSON.stringify({ personas }, null, 2)], { type: 'application/json' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = 'personas.json'
    a.click()
  }

  return (
    <div className="page">
      <div className="session-head">
        <div>
          <h2>Persona agents <span className="muted small">({personas.length})</span></h2>
          <div className="muted small">Simulated customers/users with personalities. Each one talks to the model under test, then rates it on {DIMENSIONS.join(', ')} weighted by its own priorities.</div>
        </div>
        <div className="head-actions">
          <button className="run-button small" onClick={exportAll}>⇩ Export JSON</button>
          <button className="close-button" onClick={async () => { if (confirm('Restore the 5 built-in personas to their shipped definitions?')) apply((await resetPersonas()).personas) }}>Reset built-ins</button>
        </div>
      </div>
      {error && <div className="error-text">{error}</div>}
      {message && <div className="ok-text">{message}</div>}

      <div className="agent-grid">
        {personas.map((p) => (
          <div key={p.id} className="panel persona-card">
            <div className="agent-card-head">
              <div className="agent-avatar big">{p.avatar}</div>
              <div className="grow">
                <div className="agent-name">{p.name} {p.builtin && <span className="pill">built-in</span>}</div>
                <div className="muted small">{p.tagline}</div>
              </div>
            </div>
            <div className="muted small">{p.age ? `${p.age} · ` : ''}{p.occupation} · {p.expertise_level} · lang {p.language}</div>
            <div className="chips small-chips">{p.personality_traits.map((t) => <span key={t} className="chip">{t}</span>)}</div>
            <div className="persona-meta">
              <span>patience {p.patience}/10</span><span>strictness {p.strictness}/10</span>
            </div>
            <div className="ratings-bars compact">
              {DIMENSIONS.map((d) => (
                <div key={d} className="rating-row"><span className="rating-name">{d}</span><ScoreBar value={(p.priorities[d] ?? 0) * 100} height={5} color="var(--accent-2)" /><span className="rating-val">{Math.round((p.priorities[d] ?? 0) * 100)}%</span></div>
              ))}
            </div>
            <div className="scenario"><b>Scenario:</b> {p.scenario.title}<div className="muted small ellipsis-2">“{p.scenario.opening_message}”</div></div>
            <div className="card-actions">
              <button className="link-button" onClick={() => { setEditing(p); setDraft(JSON.stringify(p, null, 2)) }}>edit JSON</button>
              <button className="link-button danger" onClick={async () => { if (confirm(`Delete persona ${p.name}?`)) { await deletePersona(p.id); apply(personas.filter((x) => x.id !== p.id)) } }}>delete</button>
            </div>
          </div>
        ))}
      </div>

      <section className="panel import-panel">
        <h3>Import personalities</h3>
        <p className="muted small">Paste JSON (one persona, a list, or <code>{'{"personas": [...]}'}</code>) or upload a file. Required: <code>name</code> and <code>scenario.opening_message</code>; everything else has defaults. Priorities are normalised server-side.</p>
        <textarea className="field-input mono" rows={10} value={importText} onChange={(e) => setImportText(e.target.value)} placeholder={JSON.stringify(TEMPLATE, null, 2)} />
        <div className="form-actions">
          <button className="run-button small" disabled={!importText.trim()} onClick={() => void doImport(importText)}>Import pasted JSON</button>
          <button className="run-button small" onClick={() => fileRef.current?.click()}>Upload .json file</button>
          <input ref={fileRef} type="file" accept="application/json,.json" hidden onChange={(e) => onFile(e.target.files?.[0])} />
          <button className="link-button" onClick={() => setImportText(JSON.stringify(TEMPLATE, null, 2))}>load example (Diego)</button>
        </div>
      </section>

      {editing && (
        <div className="modal-backdrop" onClick={() => setEditing(null)}>
          <div className="modal panel" onClick={(e) => e.stopPropagation()}>
            <h3>Edit {editing.name}</h3>
            <textarea className="field-input mono" rows={22} value={draft} onChange={(e) => setDraft(e.target.value)} />
            <div className="form-actions">
              <button className="run-button small" onClick={async () => {
                try {
                  const updated = await updatePersona(editing.id, JSON.parse(draft))
                  apply(personas.map((p) => (p.id === editing.id ? updated : p)))
                  setEditing(null)
                } catch (err) { setError(err instanceof Error ? err.message : String(err)) }
              }}>Save</button>
              <button className="close-button" onClick={() => setEditing(null)}>Cancel</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
