"""天気エージェント — wttr.in API で気象データを取得する

APIキー不要。無料の wttr.in を直接呼び出し、JSON 形式で気象データを取得する。

使用方法:
    text = get_weather("東京", date_offset=1)
    # → "明日の東京: 曇り、最高14℃/最低7℃、降水確率60%"
"""
from __future__ import annotations

import urllib.parse
from typing import Optional

from fastapi import APIRouter

router = APIRouter(prefix="/weather", tags=["weather"])

# 英語の天気説明 → 日本語
_DESC_JA: dict[str, str] = {
    "Sunny": "晴れ",
    "Clear": "晴れ",
    "Partly cloudy": "晴れ時々曇り",
    "Cloudy": "曇り",
    "Overcast": "曇り",
    "Mist": "霧",
    "Fog": "霧",
    "Freezing fog": "濃霧",
    "Patchy rain possible": "所により雨",
    "Patchy snow possible": "所により雪",
    "Patchy sleet possible": "みぞれ",
    "Light drizzle": "霧雨",
    "Freezing drizzle": "凍雨",
    "Heavy freezing drizzle": "強い凍雨",
    "Patchy light drizzle": "所により霧雨",
    "Patchy light rain": "所により小雨",
    "Light rain": "小雨",
    "Moderate rain": "雨",
    "Heavy rain": "大雨",
    "Light freezing rain": "凍雨",
    "Moderate or heavy freezing rain": "強い凍雨",
    "Light sleet": "みぞれ",
    "Moderate or heavy sleet": "強いみぞれ",
    "Patchy light snow": "所により小雪",
    "Light snow": "小雪",
    "Moderate snow": "雪",
    "Heavy snow": "大雪",
    "Blizzard": "猛吹雪",
    "Thundery outbreaks possible": "雷雨の可能性",
    "Patchy light rain with thunder": "雷を伴う小雨",
    "Moderate or heavy rain with thunder": "雷雨",
    "Patchy light snow with thunder": "雷を伴う小雪",
    "Moderate or heavy snow with thunder": "雷雪",
    "Light rain shower": "にわか雨",
    "Moderate or heavy rain shower": "強いにわか雨",
    "Torrential rain shower": "豪雨",
    "Light snow showers": "にわか雪",
    "Moderate or heavy snow showers": "強いにわか雪",
    "Light showers of ice pellets": "小雹",
    "Moderate or heavy showers of ice pellets": "雹",
    "Ice pellets": "雹",
}

_DATE_LABEL = ["今日", "明日", "明後日"]


def _desc_ja(desc: str) -> str:
    """英語の天気説明を日本語に変換する。辞書にない場合はそのまま返す。"""
    return _DESC_JA.get(desc, desc)


def get_weather(city: str, date_offset: int = 0) -> str:
    """指定都市・日付の天気をテキストで返す。

    Args:
        city:        都市名（日本語 or 英語）例: "東京", "Tokyo"
        date_offset: 0=今日, 1=明日, 2=明後日

    Returns:
        天気情報テキスト。取得失敗時はエラーメッセージ。
    """
    import httpx

    date_offset = min(max(date_offset, 0), 2)
    encoded = urllib.parse.quote(city)

    try:
        resp = httpx.get(
            f"https://wttr.in/{encoded}?format=j1",
            headers={"Accept-Language": "ja"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        return f"{city}の天気情報を取得できませんでした（{exc}）"

    try:
        weather_day = data["weather"][date_offset]
        max_temp = weather_day.get("maxtempC", "?")
        min_temp = weather_day.get("mintempC", "?")
        date_str = weather_day.get("date", "")

        # 代表時間帯（昼12時）の天気説明と降水確率を取得
        hourly = weather_day.get("hourly", [])
        noon = next((h for h in hourly if h.get("time") in ("1200", "1100")), hourly[4] if len(hourly) > 4 else None)
        if noon:
            desc_en = (noon.get("weatherDesc") or [{}])[0].get("value", "")
            rain_chance = noon.get("chanceofrain", "?")
            precip_mm = float(noon.get("precipMM", 0))
        else:
            desc_en = (weather_day.get("hourly", [{}])[0].get("weatherDesc") or [{}])[0].get("value", "")
            rain_chance = "?"
            precip_mm = 0.0

        desc_ja = _desc_ja(desc_en)

        # 現在の体感温度・湿度（今日のみ）
        extra = ""
        if date_offset == 0:
            current = (data.get("current_condition") or [{}])[0]
            feels = current.get("FeelsLikeC", "")
            humidity = current.get("humidity", "")
            if feels:
                extra += f"、体感温度{feels}℃"
            if humidity:
                extra += f"、湿度{humidity}%"

        label = _DATE_LABEL[date_offset]
        return (
            f"{label}の{city}の天気（{date_str}）: {desc_ja}、"
            f"最高{max_temp}℃/最低{min_temp}℃、降水確率{rain_chance}%"
            f"{'、降水量' + str(precip_mm) + 'mm' if precip_mm > 0 else ''}"
            f"{extra}"
        )

    except (KeyError, IndexError, TypeError) as exc:
        return f"{city}の天気データの解析に失敗しました（{exc}）"


@router.get("/")
async def weather_endpoint(city: str = "東京", days: int = 0) -> dict:
    """天気情報を返す（デバッグ用エンドポイント）。"""
    import asyncio
    text = await asyncio.to_thread(get_weather, city, days)
    return {"city": city, "days": days, "weather": text}
