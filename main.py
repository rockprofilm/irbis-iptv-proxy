import os
import logging
import subprocess
import requests
from flask import Flask, redirect, abort

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("IPTV_Proxy")

app = Flask(__name__)
VK_LIVE_URL = "https://live.vkvideo.ru/irbis_tv"

def get_vk_stream_url() -> str:
    """
    Получает актуальную HLS-ссылку напрямую с VK Live через публичный API.
    """
    try:
        # Используем встроенный публичный JSON-эндпоинт VK Video для получения данных трансляции
        channel_name = "irbis_tv"
        api_url = f"https://live.vkvideo.ru/api/v1/video/stream/{channel_name}"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": VK_LIVE_URL
        }
        
        response = requests.get(api_url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            # Извлекаем прямую ссылку на маплист из ответа VK API
            streams = data.get("data", {}).get("streams", [])
            for stream in streams:
                if stream.get("url"):
                    return stream.get("url")
                    
        # Запасной вариант через альтернативный эндпоинт метаданных
        meta_url = f"https://live.vkvideo.ru/api/v1/channel/{channel_name}"
        meta_resp = requests.get(meta_url, headers=headers, timeout=10)
        if meta_resp.status_code == 200:
            meta_data = meta_resp.json()
            hls_url = meta_data.get("data", {}).get("channel", {}).get("playback", {}).get("hls")
            if hls_url:
                return hls_url

        raise Exception("VK Live API did not return stream URL")

    except Exception as e:
        logger.exception(f"Error extracting VK stream: {e}")
        raise

@app.route("/")
def index():
    return "Irbis TV Direct Proxy is Running!"

@app.route("/stream/irbis.m3u8")
def proxy_stream():
    try:
        fresh_url = get_vk_stream_url()
        return redirect(fresh_url, code=302)
    except Exception:
        abort(502, description="Failed to fetch direct stream from VK Live")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
