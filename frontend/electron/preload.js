const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('electronAPI', {
  platform: process.platform,
  // システムトレイ・グローバルホットキーからの録音開始イベントを受け取る
  onStartRecording: (callback) => {
    ipcRenderer.on('start-recording', (_event) => callback())
  },
  // 外部 URL をデフォルトブラウザで開く（YouTube 再生など）
  openExternal: (url) => ipcRenderer.invoke('open-external', url),
})
