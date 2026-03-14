const { app, BrowserWindow, Tray, Menu, globalShortcut, nativeImage, session, shell, ipcMain } = require('electron')
const path = require('path')
const { exec } = require('child_process')

const isDev = process.env.NODE_ENV === 'development'

// WSL2 環境では GPU が使えないため無効化してソフトウェアレンダリングに統一
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
  const MEDIA_PERMISSIONS = new Set(['media', 'microphone', 'audioCapture'])

  session.defaultSession.setPermissionCheckHandler((_wc, permission, _origin, details) => {
    if (permission === 'media') {
      const t = details?.mediaType
      return t === 'audio' || t === 'unknown' || t === undefined
    }
    return MEDIA_PERMISSIONS.has(permission)
  })

  session.defaultSession.setPermissionRequestHandler((_wc, permission, callback) => {
    callback(MEDIA_PERMISSIONS.has(permission))
  })
}

/**
 * WSL2 で Ollama + FastAPI バックエンドをバックグラウンド起動する。
 * スクリプトは ollama・uvicorn 両方の起動確認後に終了するため、
 * プロセスが WSL2 セッション終了で kill されることはない。
 * 失敗した場合は retryDelay ms 後にリトライする。
 */
function launchBackend(retryDelay = 15_000) {
  exec(
    'wsl -- bash -c "~/projects/agent-team/scripts/start-backend.sh"',
    { timeout: 180_000 },
    (err, stdout) => {
      if (stdout) console.log('[Backend]', stdout.trim())
      if (err) {
        console.warn(`[Backend] launch failed, retry in ${retryDelay / 1000}s:`, err.message)
        setTimeout(() => launchBackend(retryDelay), retryDelay)
      }
    }
  )
}

/**
 * トレイメニューを構築して tray にセットする。
 * 「自動起動 ON/OFF」切り替え後に自分自身を再呼び出ししてメニューを更新する。
 */
function buildTrayMenu(win, tray) {
  const isAutoStart = app.isPackaged
    ? app.getLoginItemSettings().openAtLogin
    : false

  const menu = Menu.buildFromTemplate([
    {
      label: '表示',
      click: () => { win.show(); win.focus() },
    },
    {
      label: '録音開始',
      click: () => {
        win.show()
        win.focus()
        win.webContents.send('start-recording')
      },
    },
    { type: 'separator' },
    {
      label: 'Windows 起動時に自動起動',
      type: 'checkbox',
      checked: isAutoStart,
      // 開発モード（npm run dev）では動作しないため無効化
      enabled: app.isPackaged,
      click: (item) => {
        app.setLoginItemSettings({ openAtLogin: item.checked })
        buildTrayMenu(win, tray)
      },
    },
    { type: 'separator' },
    {
      label: '終了',
      click: () => {
        app.isQuitting = true
        app.quit()
      },
    },
  ])
  tray.setContextMenu(menu)
}

function createTray(win) {
  const iconPath = path.join(__dirname, 'icon.png')
  console.log('[Tray] icon path:', iconPath)
  let icon = nativeImage.createFromPath(iconPath)
  console.log('[Tray] icon isEmpty:', icon.isEmpty())

  // アイコン読み込み失敗時は 1x1 の透明画像で代替（トレイは表示される）
  if (icon.isEmpty()) {
    console.warn('[Tray] icon load failed, using fallback')
    icon = nativeImage.createFromDataURL(
      'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVQI12NgAAIABQAABjE+ibYAAAAASUVORK5CYII='
    )
  }

  const tray = new Tray(icon)
  tray.setToolTip('音声エージェント')

  buildTrayMenu(win, tray)

  // ダブルクリックでウィンドウを表示
  tray.on('double-click', () => { win.show(); win.focus() })

  return tray
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

  // F12 で DevTools を開閉
  win.webContents.on('before-input-event', (_event, input) => {
    if (input.key === 'F12') win.webContents.toggleDevTools()
  })

  // × ボタンでウィンドウを非表示（アプリは終了しない）
  win.on('close', (event) => {
    if (!app.isQuitting) {
      event.preventDefault()
      win.hide()
    }
  })

  return win
}

app.isQuitting = false

app.whenReady().then(() => {
  launchBackend()
  setupPermissions()
  const win = createWindow()
  createTray(win)

  // グローバルホットキー: Ctrl+Shift+Space → ウィンドウ表示 + 録音開始
  globalShortcut.register('Ctrl+Shift+Space', () => {
    win.show()
    win.focus()
    win.webContents.send('start-recording')
  })

  // IPC: 外部 URL をデフォルトブラウザで開く（YouTube 再生など）
  ipcMain.handle('open-external', (_event, url) => {
    shell.openExternal(url)
  })

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('will-quit', () => {
  globalShortcut.unregisterAll()
})

// トレイ常駐のため window-all-closed での自動終了を無効化
app.on('window-all-closed', () => {
  // 何もしない（トレイに常駐）
})
