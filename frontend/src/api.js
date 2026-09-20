async function request(path, options) {
  const res = await fetch(path, options)
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `${res.status} ${res.statusText}`)
  }
  return res.json()
}

export function tailor({ jdText, jdUrl }) {
  return request('/tailor', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ jd_text: jdText || undefined, jd_url: jdUrl || undefined }),
  })
}

export function listRuns() {
  return request('/runs')
}

export function getRun(runId) {
  return request(`/runs/${encodeURIComponent(runId)}`)
}

export function revertBullet(runId, bulletId) {
  return request(`/runs/${encodeURIComponent(runId)}/bullets/${encodeURIComponent(bulletId)}/revert`, {
    method: 'POST',
  })
}

export function pdfUrl(runId, nonce) {
  return `/runs/${encodeURIComponent(runId)}/pdf${nonce ? `?t=${nonce}` : ''}`
}
