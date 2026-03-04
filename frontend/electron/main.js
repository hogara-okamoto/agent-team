const { app, BrowserWindow, session } = require('electron')
const path = require('path')

const isDev = process.env.NODE_ENV === 'development'

// WSL2 環境では GPU が使えないため無効化してソフトウェアレンダリングに統一
// /proc/version に Microsoft の文字列があれば WSL と判断する
const isWSL = (() => {
  try {
    return require('fs').readFileSync('/proc/version', 'utf8').toLowerCase().includes('microsoft')
  } catch {
    return false
  }
})()
if (isWSL) {
  app.commandLine.appendSwitch('disable-gpu')
  app.commandLine.appendSwitch('disable-software-rasterizer')
}

function setupPermissions() {
  // マイクアクセスを明示的に許可（Electron v18+ のデフォルト拒否を回避）
  // Electron 33 / Chromium 130 以降は 'microphone' / 'audioCapture' でも
  // 権限チェックが走るため、複数名を許可する。
  const MEDIA_PERMISSIONS = new Set(['media', 'microphone', 'audioCapture'])

  session.defaultSession.setPermissionCheckHandler((_wc, permission, _origin, details) => {
    if (permission === 'media') {
      // mediaType が video のみの場合はカメラ専用なので許可しない
      const t = details?.mediaType
      return t === 'audio' || t === 'unknown' || t === undefined
    }
    return MEDIA_PERMISSIONS.has(permission)
  })

  session.defaultSession.setPermissionRequestHandler((_wc, permission, callback) => {
    callback(MEDIA_PERMISSIONS.has(permission))
  })
}

function createWindow() {
  const win = new BrowserWindow({
    width: 640,
    height: 780,
    minWidth: 480,
    minHeight: 580,
    title: '音声エージェント',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  })

  if (isDev) {
    win.loadURL('http://localhost:5173')
    win.webContents.openDevTools({ mode: 'detach' })
  } else {
    win.loadFile(path.join(__dirname, '../dist/index.html'))
  }

  // F12 で DevTools を開閉（本番でも原因調査に使用可）
  win.webContents.on('before-input-event', (_event, input) => {
    if (input.key === 'F12') win.webContents.toggleDevTools()
  })
}

app.whenReady().then(() => {
  setupPermissions()
  createWindow()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})
