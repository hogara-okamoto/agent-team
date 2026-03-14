import { useRef, useState, useCallback, useEffect } from 'react'
import { encodeWAV } from '../audioUtils'
import { checkWakeWord } from '../api'

const SAMPLE_RATE = 16000

// 発話検出の閾値（RecordButton の VAD と統一）
const SPEECH_RMS_THRESHOLD = 0.01
// 発話後の無音が続いたらクリップ送信（ms）: 自然な「、」の間（~500ms）で切れないよう長めに設定
const SILENCE_AFTER_SPEECH_MS = 2500
// 最大クリップ長（ms）: ウェイクワード+長い命令に対応（例: 「岡本さん、3月15日に〜してください」）
const MAX_CLIP_DURATION_MS = 15000

/**
 * ウェイクワード検出フック。
 *
 * 動作フロー:
 *   startMonitoring() → 常時マイクをモニタリング（VAD）
 *   → 発話を検知したらクリップを収集
 *   → 無音 or 最大長 → /wakeword に送信
 *   → ウェイクワード検出 → onDetected(text) を呼ぶ
 *   → 未検出 → 次の発話を待つ（ループ継続）
 *   stopMonitoring() → マイクを閉じる
 *
 * @param {function} onDetected - ウェイクワード検出時に transcribed text を渡すコールバック
 * @param {boolean} canTrigger  - false の間はコールバックを呼ばない（処理中などに使用）
 */
export default function useWakeWord({ onDetected, canTrigger = true }) {
  const [isMonitoring, setIsMonitoring] = useState(false)

  // オーディオ関連 refs（常時ストリームを維持）
  const streamRef    = useRef(null)
  const audioCtxRef  = useRef(null)
  const processorRef = useRef(null)

  // キャプチャ状態 refs
  const samplesRef        = useRef([])
  const isCapturingRef    = useRef(false)
  const speechDetectedRef = useRef(false)
  const silenceStartRef   = useRef(null)
  const captureStartRef   = useRef(null)

  // 非同期チェック中フラグ（連続送信防止）
  const isCheckingRef = useRef(false)
  // onDetected 発火後のクールダウンフラグ（2重トリガー防止）
  const isTriggeredRef = useRef(false)

  // 最新の canTrigger を onaudioprocess 内から参照できるように ref に同期
  const canTriggerRef = useRef(canTrigger)
  useEffect(() => { canTriggerRef.current = canTrigger }, [canTrigger])

  // サンプルバッファをリセット（次の発話待ちへ移行）
  const resetCapture = () => {
    samplesRef.current        = []
    isCapturingRef.current    = false
    speechDetectedRef.current = false
    silenceStartRef.current   = null
    captureStartRef.current   = null
  }

  // バッファを WAV Blob に変換してバックエンドに送信
  const sendClipAsync = useCallback(async (samples) => {
    if (samples.length === 0) return

    isCheckingRef.current = true
    try {
      const totalLength = samples.reduce((n, c) => n + c.length, 0)
      const allSamples = new Float32Array(totalLength)
      let offset = 0
      for (const chunk of samples) {
        allSamples.set(chunk, offset)
        offset += chunk.length
      }

      const wavBuffer = encodeWAV(allSamples, SAMPLE_RATE)
      const blob = new Blob([wavBuffer], { type: 'audio/wav' })
      const result = await checkWakeWord(blob)

      if (result.detected && canTriggerRef.current && !isTriggeredRef.current) {
        isTriggeredRef.current = true
        onDetected?.(result.text)
        // 3秒のクールダウン後にリセット
        setTimeout(() => { isTriggeredRef.current = false }, 3000)
      }
    } catch {
      // ネットワークエラー等は無視してモニタリングを継続
    } finally {
      isCheckingRef.current = false
    }
  }, [onDetected])

  const startMonitoring = useCallback(async () => {
    if (streamRef.current) return // 二重起動防止
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream

      const audioCtx = new AudioContext({ sampleRate: SAMPLE_RATE })
      audioCtxRef.current = audioCtx

      const source    = audioCtx.createMediaStreamSource(stream)
      const processor = audioCtx.createScriptProcessor(4096, 1, 1)
      processorRef.current = processor

      resetCapture()

      processor.onaudioprocess = (e) => {
        const chunk = new Float32Array(e.inputBuffer.getChannelData(0))
        const rms   = Math.sqrt(chunk.reduce((sum, s) => sum + s * s, 0) / chunk.length)

        if (!isCapturingRef.current) {
          // --- 待機中: 発話開始を検知 ---
          if (rms > SPEECH_RMS_THRESHOLD) {
            isCapturingRef.current    = true
            speechDetectedRef.current = true
            captureStartRef.current   = Date.now()
            samplesRef.current        = [chunk]
          }
        } else {
          // --- キャプチャ中: サンプルを蓄積 ---
          samplesRef.current.push(chunk)

          if (rms > SPEECH_RMS_THRESHOLD) {
            speechDetectedRef.current = true
            silenceStartRef.current   = null
          } else if (speechDetectedRef.current) {
            if (silenceStartRef.current === null) {
              silenceStartRef.current = Date.now()
            } else if (Date.now() - silenceStartRef.current >= SILENCE_AFTER_SPEECH_MS) {
              // 無音が続いた → クリップ送信
              const samples = samplesRef.current
              resetCapture()
              if (!isCheckingRef.current) sendClipAsync(samples)
            }
          }

          // 最大クリップ長に達した場合は強制送信
          if (
            captureStartRef.current &&
            Date.now() - captureStartRef.current >= MAX_CLIP_DURATION_MS
          ) {
            const samples = samplesRef.current
            resetCapture()
            if (!isCheckingRef.current) sendClipAsync(samples)
          }
        }
      }

      source.connect(processor)
      processor.connect(audioCtx.destination)
      setIsMonitoring(true)
    } catch (err) {
      console.warn('[useWakeWord] マイクアクセス失敗:', err)
    }
  }, [sendClipAsync])

  const stopMonitoring = useCallback(() => {
    processorRef.current?.disconnect()
    audioCtxRef.current?.close()
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current  = null
    audioCtxRef.current = null
    processorRef.current = null
    resetCapture()
    setIsMonitoring(false)
  }, [])

  // アンマウント時にクリーンアップ
  useEffect(() => () => stopMonitoring(), [stopMonitoring])

  return { isMonitoring, startMonitoring, stopMonitoring }
}
