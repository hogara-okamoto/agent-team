# ローカル音声エージェント 開発ロードマップ

## 目的

外部にデータを送信せず、音声会話でエージェントに指示を出せる、常時起動型のローカルルートエージェントを構築する。

```
ユーザー（音声） ←→ ルートエージェント ←→ 各専門エージェント
                       （常時起動・ローカル）
```

---

## 現在の動作状況（2026-03-11 時点）

| コンポーネント | 状態 | 実装 |
|---|---|---|
| STT（音声認識） | ✅ 完了 | faster-whisper large-v3-turbo（GPU: RTX 4000 Ada / large-v3 比 8倍高速） |
| LLM（推論） | ✅ 完了 | Ollama + qwen3.5:9b（thinking: false / keep_alive 5分） |
| TTS（日本語音声合成） | ✅ 完了 | VOICEVOX（主）/ open_jtalk / Kokoro-82M 切り替え対応 |
| FastAPI バックエンド | ✅ 完了 | `/transcribe` `/chat` `/synthesize` `/health` `/email/draft` `/email/send` `/wakeword` `/search` `/calendar` |
| Electron フロントエンド | ✅ 完了 | 録音UI・会話ログ・テキスト入力 |
| マイク入力 | ✅ 完了 | Electron Web Audio API（Electron 33 / Chromium 130 対応） |
| スピーカー出力（リアルタイム） | ✅ 完了 | Electron `<Audio>` 再生 |
| エンドツーエンド会話ループ | ✅ 完了 | 録音→STT→LLM→TTS→再生 動作確認済み |
| システムトレイ常駐 | ✅ 完了 | Tray アイコン・コンテキストメニュー・×で非表示 |
| グローバルホットキー | ✅ 完了 | Ctrl+Shift+Space で表示＋録音自動開始 |
| 無音自動停止（VAD） | ✅ 完了 | 発話後 3 秒無音で録音を自動停止（RMS閾値 0.005） |
| ウェイクワード呼び出し | ✅ 完了 | 「エージェント」「岡本」発話で自動録音開始（Whisper 判定） |
| Windows 自動起動 | ✅ 完了 | portable .exe + app.setLoginItemSettings + start-backend.sh |
| メール送信エージェント | ✅ 完了 | 音声でアポ依頼 → クライアント検索 → LLM でメール文案生成 → Gmail 送信 |
| ルートエージェント振り分け | ✅ 完了 | `intent_classifier.py` — キーワード+LLM ハイブリッド分類（email / web_search / calendar / general） |
| Web 検索エージェント | ✅ 完了 | Google Custom Search API 優先・DuckDuckGo フォールバック・LLM コンテキスト注入 |
| カレンダーエージェント（ローカル） | ✅ 完了 | ローカル JSON 保存（`backend/data/calendar.json`）・予定追加・確認 |
| 日付・曜日の正確な回答 | ✅ 完了 | バックエンドで計算した日付情報を LLM コンテキストに注入 |

---

## 2段階アプローチ

### フェーズ1：Electron フロントエンドで音声 I/O を解決 ✅ 完了

**課題**：WSL2 はオーディオデバイスにアクセスできない。
**解決策**：Electron（Chromium）が Windows のマイク／スピーカーを直接使い、WSL2 バックエンドへ HTTP で音声データを送受信する。

```
┌──────────────────────────────────────┐
│  Electron アプリ（Windows上で動作）   │
│                                      │
│  マイク → Web Audio API              │
│        ↓ WAV (HTTP POST)             │
│  ←←← WAV 受信 → <Audio> 再生        │
└───────────────┬──────────────────────┘
                │ localhost HTTP
┌───────────────▼──────────────────────┐
│  FastAPI バックエンド（WSL2）         │
│                                      │
│  /transcribe  ← WAV → STT           │
│  /chat        ← テキスト → LLM      │
│  /synthesize  ← テキスト → TTS→WAV  │
└──────────────────────────────────────┘
```

**作業リスト**

- [x] `backend/` : 既存コードを FastAPI でラップ（`/transcribe` `/chat` `/synthesize`）
- [x] `frontend/` : Electron + React でマイク録音 UI を実装
- [x] エンドツーエンドの会話ループを接続・動作確認

**解決した技術課題**

| 課題 | 解決策 |
|---|---|
| Electron でマイクが使えない | `session.setPermissionRequestHandler` でメディアアクセスを許可（Electron 33 / Chromium 130 の権限名変更に対応） |
| 日本語フォントが□□□になる | Noto Sans CJK JP をシステムインストール＋Google Fonts フォールバック |
| バックエンド起動失敗で全体クラッシュ | lifespan 内で各コンポーネントの初期化エラーを捕捉し 503 で継続 |
| WAV 形式の互換性 | Web Audio API + 手書き WAV エンコーダで PCM→WAV 変換（soundfile 互換） |
| config.yaml が読み込めない | `dependencies.py` の設定ファイルパスを絶対パスに修正 |
| open_jtalk で長文が途中で切れる | 文をセンテンス単位に分割し WAV を結合（`_split_sentences` + `_concat_wavs`） |
| TTS が `**` マークダウンで停止する | `_strip_markdown()` でマークダウン記号を除去 / system_prompt で LLM に禁止指示 |
| TTS 末尾の音が不自然に伸びる | 末尾無音をトリム（`_trim_trailing_silence`）＋文末に `。` を付加して prosody を安定化 |
| open_jtalk の音質が長文で劣化 | 20文字以下のチャンクに分割して合成（`_BREAK_RE` + `_MAX_CHARS = 20`） |

---

### フェーズ2：システムトレイ常駐型エージェントへ進化 ✅ 完了

**目標**：常時バックグラウンド起動、ホットキーまたは音声で即呼び出し。

```
Windows 起動時に自動起動
  → システムトレイに常駐
  → ホットキー（例: Ctrl+Shift+Space）で会話ウィンドウをポップアップ
  → 会話 → エージェントへ指示 → 結果を表示＋読み上げ
```

**作業リスト**

- [x] Electron のシステムトレイ常駐設定（`Tray` + コンテキストメニュー・×で非表示）
- [x] グローバルホットキーで呼び出し（`Ctrl+Shift+Space` で録音開始）
- [x] 無音自動停止（VAD）: 発話後 3 秒無音で録音を自動停止（`RecordButton.jsx`）
- [x] ウェイクワードで呼び出し（「エージェント」「岡本」の発話で自動 STT→LLM→TTS）
- [x] Windows 起動時の自動起動設定（portable .exe + トレイメニューで ON/OFF）
- [ ] ルートエージェント → 各専門エージェント呼び出し I/F の設計
- [ ] 会話履歴の永続化

**解決した技術課題**

| 課題 | 解決策 |
|---|---|
| Vite HMR WebSocket が CSP でブロックされる | `index.html` の `connect-src` に `ws://localhost:*` を追加 |
| devcontainer と Windows が別リポジトリで git 同期できない | WSL2 から SSH で GitHub push → Windows 側で pull |
| `stopRecording` を `onaudioprocess` 内から呼べない | `stopRecordingRef` で最新の関数を保持し二重呼び出しも防止 |
| Qwen3.5 が 3 倍遅い | thinking モードがデフォルト ON → `think=False` / `config.yaml: thinking: false` で無効化 |
| Ollama クライアントとサーバーのバージョン不一致（412） | `pkill ollama && ollama serve` でサーバーを再起動 |
| Kokoro の日本語依存不足 | `pip install misaki[ja]` → fugashi + unidic-lite + pyopenjtalk を一括インストール |
| unidic 辞書データが未ダウンロード | `python -m unidic download` で辞書を取得 |
| LLM の返答に中国語が混入（qwen3.5） | system_prompt に「日本語だけで答えてください」「中国語・英語を使わないでください」を明示 |
| LLM が intent 抽出で NULL を返すことがある | 正規表現で宛先名を先に確定（確実・高速）→ LLM は fallback のみ（最大 2 回リトライ） |
| 早口で録音が途中で打ち切られる | `SILENCE_RMS_THRESHOLD` を 0.01 → 0.005 に下げ、語間の小休止で停止しないよう調整 |
| `backend/.env` が git pull で Windows 側に届かない | `.env` は `.gitignore` 対象のため git 管理外。WSL2 で作成した `.env` は push されず、Windows 側の `git pull` でも生成されない。**環境構築時に Windows 側で手動作成が必要**（`GMAIL_ADDRESS` / `GMAIL_APP_PASSWORD`） |

**ウェイクワードの技術メモ**

| 項目 | 内容 |
|---|---|
| 候補ライブラリ | [OpenWakeWord](https://github.com/dscripka/openWakeWord)（無料・オフライン）/ [Porcupine](https://github.com/Picovoice/porcupine)（非商用無料・高精度） |
| 動作方式 | Electron renderer 側で Web Audio API を常時モニタリング → 検出時に STT→LLM→TTS パイプラインを起動 |
| ホットキーとの関係 | 両方実装して設定で切り替え可能にする |

---

## 将来的な専門エージェント構成（暫定）

```
ルートエージェント
├── メール送信エージェント    ✅ 実装済み（アポイント日時の調整・Gmail 送信）
├── Web 検索エージェント      ✅ 実装済み（Google Custom Search / DuckDuckGo フォールバック）
├── カレンダーエージェント    ✅ 実装済み（ローカル JSON / 予定追加・確認）
│   └── 【次期】Google Calendar API 連携（OAuth2）
├── 見積書作成エージェント    📋 未実装（次回実装予定）
├── ファイル操作エージェント  📋 未実装
├── コード実行エージェント    📋 未実装
└── （追加予定）
```

---

## 次のアクション（フェーズ3 残タスク）

1. ~~Electron でシステムトレイアイコンを表示する~~ ✅ 完了
2. ~~グローバルホットキー（`globalShortcut`）で会話ウィンドウを呼び出す~~ ✅ 完了
3. ~~無音自動停止（VAD）を実装する~~ ✅ 完了
4. ~~ウェイクワード検出を実装する~~ ✅ 完了（Whisper 判定方式）
5. ~~Windows 起動時の自動起動~~ ✅ 完了
6. ~~メール送信エージェント（アポイント日時調整）~~ ✅ 完了
7. ~~ルートエージェントの専門エージェント振り分けロジックを設計する~~ ✅ 完了
8. ~~Web 検索エージェント（Google Custom Search / DuckDuckGo）~~ ✅ 完了
9. ~~カレンダーエージェント（ローカル JSON）~~ ✅ 完了
10. 会話履歴を SQLite または JSON ファイルで永続化する
11. **カレンダーエージェントを Google Calendar API（OAuth2）に移行する**
12. **見積書作成エージェントを実装する**（品目・数量・単価 → PDF 生成）
