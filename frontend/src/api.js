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

export async function chat(message) {
  const res = await fetch(`${API_BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail ?? 'chat error')
  return data.reply
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
