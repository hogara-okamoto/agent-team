const { contextBridge } = require('electron')

// 現時点では HTTP 直接呼び出しのため IPC 不要。
// 将来のシステムトレイ・ホットキー連携用に名前空間を予約。
contextBridge.exposeInMainWorld('electronAPI', {
  platform: process.platform,
})
