const { app, BrowserWindow, session } = require('electron')
const path = require('path')

const isDev = process.env.NODE_ENV === 'development'

function setupPermissions() {
  // マイクアクセスを明示的に許可（Electron v18+ のデフォルト拒否を回避）
  session.defaultSession.setPermissionCheckHandler((_wc, permission) => {
    return permission === 'media'
  })
  session.defaultSession.setPermissionRequestHandler((_wc, permission, callback) => {
    callback(permission === 'media')
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
