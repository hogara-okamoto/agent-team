import { useRef, useState, useEffect } from 'react'
import { encodeWAV } from '../audioUtils'

const SAMPLE_RATE = 16000

/**
 * マイク録音ボタン。
 * - 起動時に利用可能なマイクデバイスを列挙して表示
 * - Web Audio API（ScriptProcessor）で PCM を収集し WAV Blob を onRecord に渡す
 * - エラーは alert ではなく onError コールバックで親に通知
 */
export default function RecordButton({ onRecord, onError, disabled }) {
  const [isRecording, setIsRecording] = useState(false)
  const [deviceLabel, setDeviceLabel] = useState('')
  const streamRef = useRef(null)
  const audioCtxRef = useRef(null)
  const processorRef = useRef(null)
  const samplesRef = useRef([])

  // マイクデバイス名を取得（権限取得後に label が埋まる）
  useEffect(() => {
    navigator.mediaDevices
      .enumerateDevices()
      .then((devices) => {
        const mic = devices.find((d) => d.kind === 'audioinput')
        if (mic) setDeviceLabel(mic.label || 'マイク（権限付与後に名前が表示されます）')
      })
      .catch(() => {})
  }, [isRecording]) // 録音停止後に再取得（label が権限付与後に埋まるため）

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream

      // 権限取得後にデバイス名を更新
      const tracks = stream.getAudioTracks()
      if (tracks.length > 0) setDeviceLabel(tracks[0].label)

      const audioCtx = new AudioContext({ sampleRate: SAMPLE_RATE })
      audioCtxRef.current = audioCtx

      const source = audioCtx.createMediaStreamSource(stream)
      const processor = audioCtx.createScriptProcessor(4096, 1, 1)
      processorRef.current = processor
      samplesRef.current = []

      processor.onaudioprocess = (e) => {
        const chunk = new Float32Array(e.inputBuffer.getChannelData(0))
        samplesRef.current.push(chunk)
      }

      source.connect(processor)
      processor.connect(audioCtx.destination)
      setIsRecording(true)
    } catch (err) {
      // err.name 例: NotAllowedError（権限拒否）/ NotFoundError（デバイス未検出）
      onError?.(`マイクアクセス失敗 [${err.name}]: ${err.message}`)
    }
  }

  const stopRecording = async () => {
    setIsRecording(false)

    processorRef.current?.disconnect()
    await audioCtxRef.current?.close()
    streamRef.current?.getTracks().forEach((t) => t.stop())

    const totalLength = samplesRef.current.reduce((n, c) => n + c.length, 0)
    const allSamples = new Float32Array(totalLength)
    let offset = 0
    for (const chunk of samplesRef.current) {
      allSamples.set(chunk, offset)
      offset += chunk.length
    }

    const wavBuffer = encodeWAV(allSamples, SAMPLE_RATE)
    const blob = new Blob([wavBuffer], { type: 'audio/wav' })
    await onRecord(blob)
  }

  return (
    <div className="record-wrap">
      <button
        className={`record-btn ${isRecording ? 'recording' : ''}`}
        onClick={isRecording ? stopRecording : startRecording}
        disabled={disabled}
      >
        {isRecording ? '⏹ 録音停止' : '🎙 録音開始'}
      </button>
      {deviceLabel && (
        <span className="mic-label">🎤 {deviceLabel}</span>
      )}
    </div>
  )
}
