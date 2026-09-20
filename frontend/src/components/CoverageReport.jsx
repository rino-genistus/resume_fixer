function Pill({ children, tone }) {
  const tones = {
    matched: 'bg-emerald-50 text-emerald-700 ring-emerald-600/20',
    missing: 'bg-red-50 text-red-700 ring-red-600/20',
    nice: 'bg-sky-50 text-sky-700 ring-sky-600/20',
  }
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium ring-1 ring-inset ${tones[tone]}`}>
      {children}
    </span>
  )
}

export default function CoverageReport({ coverage }) {
  if (!coverage) return null
  const { must_haves_matched, must_haves_missing, nice_to_haves_matched } = coverage

  return (
    <div className="space-y-3">
      <h2 className="text-sm font-semibold text-slate-900">Keyword coverage</h2>

      {must_haves_missing.length > 0 && (
        <div className="rounded-md bg-amber-50 border border-amber-200 px-3 py-2">
          <p className="text-xs font-medium text-amber-800 mb-1.5">
            Missing must-haves — add these to master_resume.yaml if they're true. The app never adds them itself.
          </p>
          <div className="flex flex-wrap gap-1.5">
            {must_haves_missing.map((s) => (
              <Pill key={s} tone="missing">{s}</Pill>
            ))}
          </div>
        </div>
      )}

      <div className="flex flex-wrap gap-1.5">
        {must_haves_matched.map((s) => (
          <Pill key={s} tone="matched">{s}</Pill>
        ))}
        {nice_to_haves_matched.map((s) => (
          <Pill key={s} tone="nice">{s}</Pill>
        ))}
      </div>
      {must_haves_matched.length === 0 && nice_to_haves_matched.length === 0 && must_haves_missing.length === 0 && (
        <p className="text-xs text-slate-500">No JD keywords extracted.</p>
      )}
    </div>
  )
}
