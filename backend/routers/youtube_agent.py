"""YouTube エージェント — YouTube Data API v3 で動画を検索して URL を返す

環境変数:
    YOUTUBE_API_KEY  — Google Cloud Console で取得した API キー
                       (Google Custom Search と同じプロジェクトのキーを使用可)

使用方法:
    url = search_youtube("ジャズ BGM")
    # → "https://www.youtube.com/watch?v=<video_id>&autoplay=1"
"""
from __future__ import annotations

import os
from typing import Optional


def search_youtube(query: str, max_results: int = 1) -> Optional[str]:
    """YouTube Data API v3 で動画を検索し、再生 URL を返す。

    Returns:
        再生可能な YouTube URL（autoplay=1 付き）。
        API キー未設定または検索失敗時は None。
    """
    import httpx

    api_key = os.getenv("YOUTUBE_API_KEY", "")
    if not api_key:
        print("[youtube] YOUTUBE_API_KEY が設定されていません")
        return None

    # ジャズ・BGM・音楽系はプレイリスト検索の方が長時間再生できる
    # type=video で単発動画を取得（プレイリストは type=playlist）
    try:
        resp = httpx.get(
            "https://www.googleapis.com/youtube/v3/search",
            params={
                "key": api_key,
                "q": query,
                "part": "snippet",
                "type": "video",
                "maxResults": max_results,
                "relevanceLanguage": "ja",
                "videoCategoryId": "10",   # Music カテゴリ（音楽以外のクエリでも問題なし）
                "videoEmbeddable": "true",
            },
            timeout=10,
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])
        if not items:
            print(f"[youtube] 検索結果なし: {query!r}")
            return None

        video_id = items[0]["id"]["videoId"]
        title = items[0]["snippet"]["title"]
        print(f"[youtube] 再生: {title!r} (id={video_id})")
        return f"https://www.youtube.com/watch?v={video_id}&autoplay=1"

    except Exception as exc:
        print(f"[youtube] API エラー: {exc}")
        return None


def extract_youtube_query(message: str) -> str:
    """「ジャズをかけて」「YouTubeでロックを流して」などからクエリを抽出する。"""
    import re

    # 呼びかけ前置き除去
    clean = re.sub(r"^[^\s、。！？]{1,8}(?:さん|様|くん|ちゃん)?[、,\s　]+", "", message.strip())

    # 除去対象: YouTube の操作動詞・サービス名
    clean = re.sub(r"YouTube(?:で|を)?|ユーチューブ(?:で|を)?", "", clean)
    clean = re.sub(
        r"(?:かけて|流して|再生して|再生お願い|かけてください|流してください|"
        r"聴かせて|聞かせて|かけてほしい|流してほしい|再生してほしい)[^。！？]*$",
        "",
        clean,
    )
    clean = re.sub(r"(?:を|で|の)?\s*(?:BGM|音楽|曲)?$", "", clean)

    query = clean.strip().rstrip("をのでに。、！？")
    # クエリが空の場合はデフォルト
    return query if query else "BGM"
