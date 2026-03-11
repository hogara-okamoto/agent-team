const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'

export async function checkHealth() {
  const res = await fetch(`${API_BASE}/health`)
  if (!res.ok) throw new Error(`health check failed: ${res.status}`)
  return res.json()
}

export async function transcribe(audioBlob) {
  const form = new FormData()
  form.append('file', audioBlob, 'recording.wav')
  const res = await fetch(`${API_BASE}/transcribe`, { method: 'POST', body: form })
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail ?? 'transcribe error')
  return data.text
}

// chat() は { reply, action, action_params } を返す
// action === 'send_email' のとき action_params に { client_name, purpose, date_str } が入る
export async function chat(message) {
  const res = await fetch(`${API_BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail ?? 'chat error')
  return data  // { reply, action, action_params }
}

export async function emailDraft({ client_name, purpose, date_str }) {
  const res = await fetch(`${API_BASE}/email/draft`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ client_name, purpose, date_str }),
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail ?? 'email draft error')
  return data  // { to, to_name, company, subject, body, client_found }
}

export async function emailSend({ to, subject, body }) {
  const res = await fetch(`${API_BASE}/email/send`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ to, subject, body }),
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail ?? 'email send error')
  return data  // { status, to }
}

export async function synthesize(text) {
  const res = await fetch(`${API_BASE}/synthesize`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  })
  if (!res.ok) {
    const data = await res.json()
    throw new Error(data.detail ?? 'synthesize error')
  }
  return res.blob()
}

export async function checkWakeWord(audioBlob) {
  const form = new FormData()
  form.append('file', audioBlob, 'clip.wav')
  const res = await fetch(`${API_BASE}/wakeword`, { method: 'POST', body: form })
  if (!res.ok) return { detected: false, text: '' }
  return res.json()
}

export async function clearHistory() {
  const res = await fetch(`${API_BASE}/chat/history`, { method: 'DELETE' })
  return res.json()
}

// webSearch() は { query, results: [{title, body, href}], summary } を返す
export async function webSearch(query, maxResults = 5) {
  const res = await fetch(`${API_BASE}/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, max_results: maxResults }),
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail ?? 'web search error')
  return data
}
