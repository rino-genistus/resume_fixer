import { useEffect, useState } from 'react'
import * as api from './api'
import BulletDiffList from './components/BulletDiffList'
import CoverageReport from './components/CoverageReport'
import RunsSidebar from './components/RunsSidebar'

export default function App() {
  const [jdText, setJdText] = useState('')
  const [jdUrl, setJdUrl] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const [runs, setRuns] = useState([])
  const [run, setRun] = useState(null) // full detail of the currently viewed run
  const [pdfNonce, setPdfNonce] = useState(0)
  const [revertingId, setRevertingId] = useState(null)

  useEffect(() => {
    api.listRuns().then(setRuns).catch(() => {})
  }, [])

  async function loadRun(runId) {
    const detail = await api.getRun(runId)
    setRun(detail)
    setPdfNonce(Date.now())
  }

  async function handleTailor(e) {
    e.preventDefault()
    if (!jdText.trim() && !jdUrl.trim()) {
      setError('Paste a job description or enter a URL.')
      return
    }
    setError(null)
    setLoading(true)
    try {
      const result = await api.tailor({ jdText: jdText.trim(), jdUrl: jdUrl.trim() })
      await loadRun(result.run_id)
      setRuns(await api.listRuns())
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function handleRevert(bulletId) {
    if (!run) return
    setRevertingId(bulletId)
    setError(null)
    try {
      const updated = await api.revertBullet(run.run_id, bulletId)
      setRun(updated)
      setPdfNonce(Date.now())
      setRuns(await api.listRuns())
    } catch (err) {
      setError(err.message)
    } finally {
      setRevertingId(null)
    }
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white px-6 py-4">
        <h1 className="text-lg font-semibold text-slate-900">Resume Tailor</h1>
      </header>

      <div className="mx-auto max-w-6xl px-6 py-6 grid grid-cols-[200px_1fr] gap-6">
        <aside>
          <RunsSidebar runs={runs} selectedRunId={run?.run_id} onSelect={loadRun} />
        </aside>

        <main className="space-y-6">
          <form onSubmit={handleTailor} className="bg-white border border-slate-200 rounded-lg p-4 space-y-3">
            <textarea
              value={jdText}
              onChange={(e) => setJdText(e.target.value)}
              placeholder="Paste the job description here…"
              rows={8}
              className="w-full text-sm border border-slate-300 rounded-md p-2.5 focus:outline-none focus:ring-2 focus:ring-slate-400"
            />
            <div className="flex items-center gap-3">
              <input
                type="text"
                value={jdUrl}
                onChange={(e) => setJdUrl(e.target.value)}
                placeholder="...or a job posting URL"
                className="flex-1 text-sm border border-slate-300 rounded-md p-2 focus:outline-none focus:ring-2 focus:ring-slate-400"
              />
              <button
                type="submit"
                disabled={loading}
                className="shrink-0 bg-slate-900 text-white text-sm font-medium px-4 py-2 rounded-md hover:bg-slate-700 disabled:opacity-50"
              >
                {loading ? 'Tailoring…' : 'Tailor'}
              </button>
            </div>
            {loading && (
              <p className="text-xs text-slate-500">
                Extracting requirements, ranking, and rewriting bullets — this can take a minute or two.
              </p>
            )}
            {error && <p className="text-xs text-red-600">{error}</p>}
          </form>

          {run && (
            <div className="grid grid-cols-2 gap-6">
              <div className="space-y-6">
                <div className="bg-white border border-slate-200 rounded-lg p-4 flex items-center justify-between">
                  <div>
                    <p className="text-sm font-semibold text-slate-900">{run.title}</p>
                    <p className="text-xs text-slate-500">{run.company}</p>
                  </div>
                  <a
                    href={api.pdfUrl(run.run_id, pdfNonce)}
                    download={`${run.run_id}.pdf`}
                    className="text-xs font-medium px-3 py-1.5 rounded-md border border-slate-300 hover:bg-slate-50"
                  >
                    Download PDF
                  </a>
                </div>

                <div className="bg-white border border-slate-200 rounded-lg overflow-hidden" style={{ height: 640 }}>
                  <iframe
                    title="Resume preview"
                    src={api.pdfUrl(run.run_id, pdfNonce)}
                    className="w-full h-full"
                  />
                </div>
              </div>

              <div className="space-y-6">
                <div className="bg-white border border-slate-200 rounded-lg p-4">
                  <CoverageReport coverage={run.report.coverage} />
                </div>

                <div className="bg-white border border-slate-200 rounded-lg p-4 space-y-3">
                  <h2 className="text-sm font-semibold text-slate-900">Bullets: original vs. rewritten</h2>
                  <BulletDiffList bullets={run.bullets} onRevert={handleRevert} reverting={revertingId} />
                </div>
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  )
}
