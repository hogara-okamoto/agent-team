from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException

# voice-chatbot の src を import パスに追加（main.py より先に呼ばれることがあるため冗長に設定）
_vc_path = str(Path(__file__).parent.parent / "voice-chatbot")
if _vc_path not in sys.path:
    sys.path.insert(0, _vc_path)

_transcriber: Optional[Any] = None
_llm_client: Optional[Any] = None
_tts_synthesizer: Optional[Any] = None

# 初期化失敗時のエラーメッセージを保持
_init_errors: dict[str, str] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """起動時にモデルをロード、終了時にアンロードする。
    コンポーネントが欠落している場合は警告を出して続行する。
    """
    global _transcriber, _llm_client, _tts_synthesizer

    try:
        from src.config import Settings
        _config_path = Path(__file__).parent.parent / "voice-chatbot" / "config.yaml"
        settings = Settings.from_yaml(str(_config_path))
    except Exception as e:
        print(f"[WARNING] 設定ファイルの読み込みに失敗しました（デフォルト値を使用）: {e}")
        from src.config import Settings
        settings = Settings()

    # --- STT ---
    try:
        from src.stt.transcriber import WhisperTranscriber
        _transcriber = WhisperTranscriber(
            model_size=settings.stt.model,
            device=settings.stt.device,
            compute_type=settings.stt.compute_type,
            language=settings.stt.language,
            download_root=settings.stt.download_root,
        )
    except Exception as e:
        _init_errors["stt"] = str(e)
        print(f"[WARNING] STT の初期化をスキップしました: {e}")

    # --- LLM ---
    try:
        from src.llm.client import OllamaClient
        client = OllamaClient(
            model=settings.llm.model,
            base_url=settings.llm.base_url,
            system_prompt=settings.llm.system_prompt,
            keep_alive=settings.llm.keep_alive,
        )
        # Ollama サーバーへの疎通確認
        client._client.list()
        _llm_client = client
    except Exception as e:
        _init_errors["llm"] = str(e)
        print(f"[WARNING] LLM の初期化をスキップしました: {e}")

    # --- TTS ---
    try:
        from src.tts.synthesizer import (
            OpenJTalkSynthesizer, PiperSynthesizer,
            VOICEVOXSynthesizer, StyleBertVITS2Synthesizer, XTTSSynthesizer,
        )
        engine = settings.tts.engine
        if engine == "openjtalk":
            _tts_synthesizer = OpenJTalkSynthesizer(
                dict_dir=settings.tts.openjtalk_dict,
                voice_path=settings.tts.openjtalk_voice,
            )
        elif engine == "voicevox":
            _tts_synthesizer = VOICEVOXSynthesizer(
                base_url=settings.tts.voicevox_url,
                speaker=settings.tts.voicevox_speaker,
            )
        elif engine == "style_bert_vits2":
            _tts_synthesizer = StyleBertVITS2Synthesizer(
                base_url=settings.tts.style_bert_vits2_url,
                model_id=settings.tts.style_bert_vits2_model_id,
                speaker_id=settings.tts.style_bert_vits2_speaker_id,
                style=settings.tts.style_bert_vits2_style,
            )
        elif engine == "xtts":
            _tts_synthesizer = XTTSSynthesizer(
                model_name=settings.tts.xtts_model,
                language=settings.tts.xtts_language,
                speaker_wav=settings.tts.xtts_speaker_wav,
                device=settings.tts.xtts_device,
            )
        else:
            _tts_synthesizer = PiperSynthesizer(
                model_path=settings.tts.model_path,
                speaker_id=settings.tts.speaker_id,
                length_scale=settings.tts.length_scale,
            )
    except Exception as e:
        _init_errors["tts"] = str(e)
        print(f"[WARNING] TTS の初期化をスキップしました: {e}")

    print("[Backend] 起動完了")
    if _init_errors:
        print(f"[Backend] 利用不可コンポーネント: {list(_init_errors.keys())}")

    yield

    # --- Shutdown ---
    if _transcriber is not None and hasattr(_transcriber, "unload"):
        _transcriber.unload()


def get_transcriber() -> Any:
    if _transcriber is None:
        raise HTTPException(
            status_code=503,
            detail=f"STT が利用できません: {_init_errors.get('stt', '未初期化')}",
        )
    return _transcriber


def get_llm_client() -> Any:
    if _llm_client is None:
        raise HTTPException(
            status_code=503,
            detail=f"LLM が利用できません: {_init_errors.get('llm', '未初期化')}",
        )
    return _llm_client


def get_tts_synthesizer() -> Any:
    if _tts_synthesizer is None:
        raise HTTPException(
            status_code=503,
            detail=f"TTS が利用できません: {_init_errors.get('tts', '未初期化')}",
        )
    return _tts_synthesizer


def get_status() -> dict[str, str]:
    """各コンポーネントの状態を返す。"""
    return {
        "stt": "ok" if _transcriber is not None else f"unavailable: {_init_errors.get('stt', '')}",
        "llm": "ok" if _llm_client is not None else f"unavailable: {_init_errors.get('llm', '')}",
        "tts": "ok" if _tts_synthesizer is not None else f"unavailable: {_init_errors.get('tts', '')}",
    }
