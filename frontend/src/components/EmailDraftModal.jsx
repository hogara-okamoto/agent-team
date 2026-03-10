import { useState, useEffect } from 'react'
import { emailDraft, emailSend } from '../api'

/**
 * メール文案表示・確認・送信モーダル
 *
 * Props:
 *   params        - { client_name, purpose, date_str }
 *   onClose       - モーダルを閉じるコールバック
 *   onSent        - 送信成功時コールバック (sentTo: string) => void
 *   onError       - エラー時コールバック (msg: string) => void
 *   confirmText   - 音声/テキストで「OK」などが送られてきたとき親から渡される文字列
 */
export default function EmailDraftModal({ params, onClose, onSent, onError, confirmText }) {
  const [draft, setDraft] = useState(null)
  const [loading, setLoading] = useState(false)
  const [sending, setSending] = useState(false)
  const [editSubject, setEditSubject] = useState('')
  const [editBody, setEditBody] = useState('')
  const [editTo, setEditTo] = useState('')
  // purpose・date_str が未指定のとき手入力できるようにする
  const [editPurpose, setEditPurpose] = useState(params.purpose || '')
  const [editDate, setEditDate] = useState(params.date_str || '')
  const [step, setStep] = useState('input') // 'input' | 'preview'

  // purpose・date が揃っている場合は最初から文案生成へ
  useEffect(() => {
    const hasInfo = params.purpose && params.purpose !== 'ご連絡' && params.date_str && params.date_str !== '近日中'
    if (hasInfo) {
      generateDraft(params)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const generateDraft = async (p) => {
    setStep('preview')
    setLoading(true)
    try {
      const d = await emailDraft(p)
      setDraft(d)
      setEditSubject(d.subject)
      setEditBody(d.body)
      setEditTo(d.to)
    } catch (e) {
      onError(e.message)
      setStep('input')
    } finally {
      setLoading(false)
    }
  }

  const handleGenerate = () => {
    generateDraft({
      client_name: params.client_name,
      purpose: editPurpose || 'ご連絡',
      date_str: editDate || '近日中',
    })
  }

  // 親から confirmText が届いたら自動送信（preview ステップのみ）
  useEffect(() => {
    if (!confirmText || !draft || loading || sending || step !== 'preview') return
    const isOk = /^(ok|okay|はい|送信|それでよい|よし|良い|いいよ|送って)/i.test(confirmText.trim())
    if (isOk) handleSend()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [confirmText])

  const handleSend = async () => {
    if (sending || !editTo) return
    setSending(true)
    try {
      await emailSend({ to: editTo, subject: editSubject, body: editBody })
      onSent(editTo)
    } catch (e) {
      onError(e.message)
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="modal-overlay" role="dialog" aria-modal="true">
      <div className="modal">
        <div className="modal-header">
          <h2>📧 メール送信エージェント</h2>
          <button className="modal-close-btn" onClick={onClose} aria-label="閉じる">×</button>
        </div>

        {/* ── Step 1: 用件・日時の入力 ── */}
        {step === 'input' && (
          <>
            <div className="modal-field">
              <label>宛先クライアント</label>
              <div className="modal-readonly">{params.client_name} 様</div>
            </div>
            <div className="modal-field">
              <label>用件</label>
              <input
                value={editPurpose}
                onChange={(e) => setEditPurpose(e.target.value)}
                placeholder="例: ミーティングのアポイント"
                autoFocus
              />
            </div>
            <div className="modal-field">
              <label>希望日時</label>
              <input
                value={editDate}
                onChange={(e) => setEditDate(e.target.value)}
                placeholder="例: 明日、来週月曜日"
              />
            </div>
            <div className="modal-actions">
              <button className="modal-cancel-btn" onClick={onClose}>キャンセル</button>
              <button
                className="modal-send-btn"
                onClick={handleGenerate}
                disabled={!editPurpose.trim()}
              >
                文案を生成
              </button>
            </div>
          </>
        )}

        {/* ── Step 2: 文案のプレビュー・送信 ── */}
        {step === 'preview' && (
          <>
            {loading ? (
              <div className="modal-loading">文案を生成中…</div>
            ) : (
              <>
                {!draft?.client_found && (
                  <div className="modal-warn">
                    クライアントリストに見つかりませんでした。宛先を手動で入力してください。
                  </div>
                )}

                <div className="modal-field">
                  <label>宛先メールアドレス</label>
                  <input
                    value={editTo}
                    onChange={(e) => setEditTo(e.target.value)}
                    placeholder="メールアドレス"
                    disabled={sending}
                  />
                  {draft && <span className="modal-field-sub">{draft.to_name}</span>}
                </div>

                <div className="modal-field">
                  <label>件名</label>
                  <input
                    value={editSubject}
                    onChange={(e) => setEditSubject(e.target.value)}
                    disabled={sending}
                  />
                </div>

                <div className="modal-field">
                  <label>本文</label>
                  <textarea
                    value={editBody}
                    onChange={(e) => setEditBody(e.target.value)}
                    rows={10}
                    disabled={sending}
                  />
                </div>

                <div className="modal-hint">
                  「それでよい」「OK」「送信」と話しかけるか、ボタンで送信できます。
                </div>

                <div className="modal-actions">
                  <button
                    className="modal-cancel-btn"
                    onClick={() => setStep('input')}
                    disabled={sending}
                  >
                    ← 修正
                  </button>
                  <button className="modal-cancel-btn" onClick={onClose} disabled={sending}>
                    キャンセル
                  </button>
                  <button
                    className="modal-send-btn"
                    onClick={handleSend}
                    disabled={sending || !editTo}
                  >
                    {sending ? '送信中…' : '送信する'}
                  </button>
                </div>
              </>
            )}
          </>
        )}
      </div>
    </div>
  )
}
