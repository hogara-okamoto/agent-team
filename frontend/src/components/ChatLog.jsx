import { useEffect, useRef } from 'react'

export default function ChatLog({ messages }) {
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  if (messages.length === 0) {
    return (
      <div className="chat-log empty">
        <p>🎙️ 録音ボタンを押して話しかけるか、テキストで入力してください</p>
      </div>
    )
  }

  return (
    <div className="chat-log">
      {messages.map((msg) => (
        <div key={msg.id} className={`message ${msg.role}`}>
          <span className="message-label">{msg.role === 'user' ? 'あなた' : 'AI'}</span>
          <p className="message-text">{msg.text}</p>
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  )
}
