import { useState, useEffect } from 'react'
import { checkHealth, transcribe, chat, synthesize, clearHistory } from './api'
import ChatLog from './components/ChatLog'
import RecordButton from './components/RecordButton'

// 会話処理の状態
// 'idle' | 'recording' | 'transcribing' | 'thinking' | 'synthesizing'
const STATUS_LABEL = {
  idle: '',
  transcribing: '🔄 音声認識中…',
  thinking: '🤔 考え中…',
  synthesizing: '🔊 音声合成中…',
}

export default function App() {
  const [messages, setMessages] = useState([])
  const [status, setStatus] = useState('idle')
  const [health, setHealth] = useState(null)
  const [textInput, setTextInput] = useState('')
  const [errorMsg, setErrorMsg] = useState('')
  // トレイ/ホットキーから録音開始を受け取るカウンター
  const [recordTrigger, setRecordTrigger] = useState(0)

  // 起動時にバックエンドのヘルスを確認
  useEffect(() => {
    checkHealth()
      .then(setHealth)
      .catch(() => setHealth({ status: 'error', components: {} }))
  }, [])

  // システムトレイ・グローバルホットキーからの録音開始イベントを購読
  useEffect(() => {
    window.electronAPI?.onStartRecording?.(() => {
      setRecordTrigger((t) => t + 1)
    })
  }, [])

  const appendMessage = (role, text) =>
    setMessages((prev) => [...prev, { role, text, id: Date.now() + Math.random() }])

  const playAudio = (blob) => {
    const url = URL.createObjectURL(blob)
    const audio = new Audio(url)
    audio.onended = () => URL.revokeObjectURL(url)
    audio.play().catch(console.warn)
  }

  // 録音完了後の処理: STT → LLM → TTS
  const handleRecord = async (audioBlob) => {
    setErrorMsg('')
    try {
      setStatus('transcribing')
      const userText = await transcribe(audioBlob)
      if (!userText.trim()) {
        setStatus('idle')
        return
      }
      appendMessage('user', userText)
      await replyWithLLM(userText)
    } catch (err) {
      setErrorMsg(err.message)
    } finally {
      setStatus('idle')
    }
  }

  // テキスト入力からの処理: LLM → TTS
  const handleTextSubmit = async () => {
    const userText = textInput.trim()
    if (!userText || status !== 'idle') return
    setTextInput('')
    setErrorMsg('')
    appendMessage('user', userText)
    try {
      await replyWithLLM(userText)
    } catch (err) {
      setErrorMsg(err.message)
    } finally {
      setStatus('idle')
    }
  }

  const replyWithLLM = async (userText) => {
    setStatus('thinking')
    const replyText = await chat(userText)
    appendMessage('assistant', replyText)

    // TTS が使えない場合はエラーを無視してテキスト表示のみ
    try {
      setStatus('synthesizing')
      const wavBlob = await synthesize(replyText)
      playAudio(wavBlob)
    } catch {
      // TTS 未対応環境では無音のまま続行
    }
  }

  const handleClearHistory = async () => {
    await clearHistory().catch(console.warn)
    setMessages([])
    setErrorMsg('')
  }

  const isProcessing = status !== 'idle'

  return (
    <div className="app">
      <header className="app-header">
        <h1>🎙 音声エージェント</h1>
        <HealthBadges health={health} />
      </header>

      <ChatLog messages={messages} />

      {STATUS_LABEL[status] && (
        <div className="status-indicator">{STATUS_LABEL[status]}</div>
      )}

      {errorMsg && (
        <div className="error-banner" role="alert">
          ⚠️ {errorMsg}
        </div>
      )}

      <footer className="app-footer">
        <div className="text-input-row">
          <input
            type="text"
            value={textInput}
            onChange={(e) => setTextInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleTextSubmit()}
            placeholder="テキストで入力（Enter で送信）"
            disabled={isProcessing}
          />
          <button
            onClick={handleTextSubmit}
            disabled={isProcessing || !textInput.trim()}
            className="send-btn"
          >
            送信
          </button>
        </div>

        <div className="action-row">
          <RecordButton
            onRecord={handleRecord}
            onError={setErrorMsg}
            disabled={isProcessing}
            externalTrigger={recordTrigger}
          />
          <button
            className="clear-btn"
            onClick={handleClearHistory}
            disabled={isProcessing}
          >
            履歴クリア
          </button>
        </div>
      </footer>
    </div>
  )
}

function HealthBadges({ health }) {
  if (!health) return <span className="health-loading">接続確認中…</span>
  if (health.status === 'error') return <span className="badge ng">バックエンド未接続</span>

  const { components = {} } = health
  return (
    <div className="health-badges">
      {Object.entries(components).map(([name, val]) => (
        <span key={name} className={`badge ${val === 'ok' ? 'ok' : 'ng'}`}>
          {name.toUpperCase()} {val === 'ok' ? '✓' : '✗'}
        </span>
      ))}
    </div>
  )
}
