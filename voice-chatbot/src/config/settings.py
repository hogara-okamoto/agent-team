from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, field_validator


class STTConfig(BaseModel):
    model: str = "small"
    language: str = "ja"
    device: str = "cuda"
    compute_type: str = "float16"
    download_root: str = "models/whisper"

    @field_validator("device")
    @classmethod
    def validate_device(cls, v: str) -> str:
        if v == "cuda":
            try:
                import ctranslate2

                if ctranslate2.get_cuda_device_count() == 0:
                    print("[Warning] CUDA デバイスが見つかりません。CPU にフォールバックします。")
                    return "cpu"
            except Exception:
                return "cpu"
        return v

    @field_validator("compute_type")
    @classmethod
    def adjust_compute_type(cls, v: str, info) -> str:
        # CPU 時は float16 非対応なので int8 に変更
        device = info.data.get("device", "cuda")
        if device == "cpu" and v == "float16":
            return "int8"
        return v


class LLMConfig(BaseModel):
    model: str = "llama3.2:3b"
    base_url: str = "http://localhost:11434"
    keep_alive: int = 0
    system_prompt: str = "あなたは親切なアシスタントです。簡潔に日本語で答えてください。"


class TTSConfig(BaseModel):
    engine: str = "openjtalk"  # openjtalk / voicevox / style_bert_vits2 / xtts / piper

    # openjtalk 設定
    openjtalk_dict: str = "/var/lib/mecab/dic/open-jtalk/naist-jdic"
    openjtalk_voice: str = "/usr/share/hts-voice/nitech-jp-atr503-m001/nitech_jp_atr503_m001.htsvoice"

    # voicevox 設定
    voicevox_url: str = "http://localhost:50021"
    voicevox_speaker: int = 3  # 3=ずんだもん, 1=四国めたん, 8=春日部つむぎ

    # style_bert_vits2 設定
    style_bert_vits2_url: str = "http://localhost:5000"
    style_bert_vits2_model_id: int = 0
    style_bert_vits2_speaker_id: int = 0
    style_bert_vits2_style: str = "Neutral"

    # xtts 設定
    xtts_model: str = "tts_models/multilingual/multi-dataset/xtts_v2"
    xtts_language: str = "ja"
    xtts_speaker_wav: str = ""   # 必須: 6〜10 秒の日本語 WAV ファイルパス
    xtts_device: str = "cuda"

    # piper 設定（engine: piper の場合のみ使用）
    model_path: str = "models/tts/ja_JP-test-medium.onnx"
    speaker_id: Optional[int] = None
    length_scale: float = 1.0


class AudioConfig(BaseModel):
    sample_rate: int = 16000
    chunk_duration: float = 0.1
    silence_threshold: float = 0.02
    silence_duration: float = 1.5
    max_record_duration: float = 30.0


class Settings(BaseModel):
    stt: STTConfig = STTConfig()
    llm: LLMConfig = LLMConfig()
    tts: TTSConfig = TTSConfig()
    audio: AudioConfig = AudioConfig()

    @classmethod
    def from_yaml(cls, path: str = "config.yaml") -> "Settings":
        yaml_path = Path(path)
        if yaml_path.exists():
            with open(yaml_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            return cls(**data)
        return cls()
