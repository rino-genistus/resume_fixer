export default function RunsSidebar({ runs, selectedRunId, onSelect }) {
  return (
    <div className="space-y-1">
      <h2 className="text-sm font-semibold text-slate-900 mb-2">Past runs</h2>
      {runs.length === 0 && <p className="text-xs text-slate-500">No runs yet.</p>}
      {runs.map((run) => (
        <button
          key={run.run_id}
          type="button"
          onClick={() => onSelect(run.run_id)}
          className={`w-full text-left px-2.5 py-2 rounded-md text-xs border ${
            run.run_id === selectedRunId
              ? 'bg-slate-900 text-white border-slate-900'
              : 'border-transparent hover:bg-slate-100 text-slate-700'
          }`}
        >
          <p className="font-medium truncate">{run.title}</p>
          <p className={`truncate ${run.run_id === selectedRunId ? 'text-slate-300' : 'text-slate-500'}`}>
            {run.company}
          </p>
        </button>
      ))}
    </div>
  )
}
