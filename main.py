import os
import logging
import requests
from flask import Flask, redirect, abort

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("IPTV_Proxy")

app = Flask(__name__)
API_BASE = "https://birgetv.platform24.tv"

def fetch_fresh_stream_url() -> str:
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://app.birge.tv/"
    })

    try:
        # Прямой запрос списка каналов или ресурсов платформы без авторизации пользователя, 
        # чтобы получить валидные куки и сессионные параметры CDN
        logger.info("Запрос конфигурации платформы...")
        init_resp = session.get(f"{API_BASE}/v2/platform/configuration", timeout=10)
        
        # ID канала Irbis TV в системе Birge TV (подставьте актуальный числовой ID)
        channel_id = 142 

        logger.info(f"Запрос прямой ссылки на поток для канала ID {channel_id}...")
        
        stream_response = session.get(
            f"{API_BASE}/v2/channels/{channel_id}/stream",
            timeout=10
        )

        if stream_response.status_code != 200:
            logger.error(f"Ошибка API стрима: {stream_response.status_code} - {stream_response.text}")
            raise Exception("Stream endpoint returned error")

        stream_data = stream_response.json()
        
        # Извлекаем URL потока
        hls_url = (
            stream_data.get("url") or 
            stream_data.get("data", {}).get("url") or
            stream_data.get("stream", {}).get("url")
        )
        
        if not hls_url:
            variants = stream_data.get("variants") or stream_data.get("data", {}).get("variants", [])
            if variants and isinstance(variants, list):
                hls_url = variants[0].get("url")

        if not hls_url:
            logger.error(f"В ответе нет поля с URL: {stream_data}")
            raise Exception("HLS URL not found in API response")

        return hls_url

    except Exception as e:
        logger.exception(f"Error fetching stream: {e}")
        raise

@app.route("/")
def index():
    return "IPTV Proxy Server for Irbis TV is Running!"

@app.route("/stream/irbis.m3u8")
def proxy_stream():
    try:
        fresh_url = fetch_fresh_stream_url()
        return redirect(fresh_url, code=302)
    except Exception:
        abort(502, description="Failed to fetch stream from Platform24")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
