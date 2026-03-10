const { app, BrowserWindow, Tray, Menu, globalShortcut, nativeImage, session } = require('electron')
const path = require('path')
const { exec, spawn } = require('child_process')

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

let backendProcess = null

/**
 * WSL2 で Ollama + FastAPI バックエンドを起動する。
 * uvicorn は spawn でフォアグラウンド実行し WSL セッションを維持する
 * （セッション終了による WSL2 自動シャットダウンを防ぐため）。
 */
function launchBackend(retryDelay = 15_000) {
  // Ollama を起動（既に起動済みならスキップ）
  exec('wsl -- bash -c "mkdir -p ~/.local/log/voice-agent && pgrep -x ollama > /dev/null || nohup ollama serve > ~/.local/log/voice-agent/ollama.log 2>&1 &"')

  // uvicorn をフォアグラウンドで起動（WSL セッションを維持するため spawn を使用）
  backendProcess = spawn('wsl', [
    '--', 'bash', '-c',
    'source ~/projects/agent-team/.venv/bin/activate && ' +
    'cd ~/projects/agent-team/backend && ' +
    'uvicorn main:app --host 0.0.0.0 --port 8000'
  ], { stdio: ['ignore', 'pipe', 'pipe'] })

  backendProcess.stdout.on('data', d => console.log('[Backend]', d.toString().trim()))
  backendProcess.stderr.on('data', d => console.log('[Backend]', d.toString().trim()))

  backendProcess.on('exit', (code, signal) => {
    backendProcess = null
    if (!app.isQuitting) {
      console.warn(`[Backend] exited (code=${code} signal=${signal}), retry in ${retryDelay / 1000}s`)
      setTimeout(() => launchBackend(retryDelay), retryDelay)
    }
  })
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

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('will-quit', () => {
  globalShortcut.unregisterAll()
  if (backendProcess) backendProcess.kill()
})

// トレイ常駐のため window-all-closed での自動終了を無効化
app.on('window-all-closed', () => {
  // 何もしない（トレイに常駐）
})
