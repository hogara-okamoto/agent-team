/**
 * Float32Array の PCM サンプルを WAV バイナリにエンコードする。
 * MediaRecorder が webm しか出力できない Chromium 環境で使用する。
 *
 * @param {Float32Array} samples  モノラル PCM（-1.0 〜 1.0）
 * @param {number} sampleRate     サンプリングレート（Hz）
 * @returns {ArrayBuffer}         WAV バイナリ
 */
export function encodeWAV(samples, sampleRate) {
  const dataLength = samples.length * 2 // int16 = 2 bytes/sample
  const buffer = new ArrayBuffer(44 + dataLength)
  const view = new DataView(buffer)

  // RIFF chunk descriptor
  writeString(view, 0, 'RIFF')
  view.setUint32(4, 36 + dataLength, true)
  writeString(view, 8, 'WAVE')

  // fmt sub-chunk
  writeString(view, 12, 'fmt ')
  view.setUint32(16, 16, true)          // PCM fmt chunk size
  view.setUint16(20, 1, true)           // PCM format
  view.setUint16(22, 1, true)           // mono
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate * 2, true) // byte rate
  view.setUint16(32, 2, true)           // block align
  view.setUint16(34, 16, true)          // bits per sample

  // data sub-chunk
  writeString(view, 36, 'data')
  view.setUint32(40, dataLength, true)

  // PCM data: float32 → int16
  let offset = 44
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]))
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true)
    offset += 2
  }

  return buffer
}

function writeString(view, offset, str) {
  for (let i = 0; i < str.length; i++) {
    view.setUint8(offset + i, str.charCodeAt(i))
  }
}
