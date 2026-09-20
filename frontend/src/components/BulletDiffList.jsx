function BulletRow({ bullet, onRevert, reverting }) {
  const changed = bullet.final !== bullet.original
  const canRevert = changed
  const busy = reverting === bullet.bullet_id

  return (
    <div className="border border-slate-200 rounded-md p-3 space-y-2">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0 space-y-1.5">
          <div>
            <p className="text-[10px] uppercase tracking-wide text-slate-400 font-medium">Original</p>
            <p className="text-sm text-slate-600">{bullet.original}</p>
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-wide text-slate-400 font-medium">
              {changed ? 'Rewritten' : 'Unchanged'}
            </p>
            <p className={`text-sm ${changed ? 'text-slate-900 font-medium' : 'text-slate-500'}`}>{bullet.final}</p>
          </div>
        </div>
        <button
          type="button"
          disabled={!canRevert || busy}
          onClick={() => onRevert(bullet.bullet_id)}
          className="shrink-0 text-xs font-medium px-2.5 py-1.5 rounded-md border border-slate-300 text-slate-700 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {busy ? 'Reverting…' : 'Revert'}
        </button>
      </div>
      {!bullet.accepted && (
        <p className="text-xs text-red-600">
          Rejected rewrite kept as original — {bullet.reason}
        </p>
      )}
    </div>
  )
}

export default function BulletDiffList({ bullets, onRevert, reverting }) {
  if (!bullets || bullets.length === 0) {
    return <p className="text-xs text-slate-500">No bullets selected for this run.</p>
  }
  return (
    <div className="space-y-2">
      {bullets.map((b) => (
        <BulletRow key={b.bullet_id} bullet={b} onRevert={onRevert} reverting={reverting} />
      ))}
    </div>
  )
}
