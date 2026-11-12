import os
import logging
import requests
from flask import Flask, redirect, abort

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("IPTV_Proxy")

app = Flask(__name__)
API_BASE = "https://birgetv.platform24.tv"

def resolve_irbis_channel_id(session: requests.Session, token: str) -> int:
    """
    Динамически находит реальный numeric ID для канала со slug 'irbis-tv' 
    или названием 'Ирбис' через API Birge TV, обходя клиентскую логику channelMapBySlug.
    """
    try:
        # Запрашиваем полный список категорий/каналов с токеном авторизации
        response = session.get(
            f"{API_BASE}/v2/channels/category_list",
            params={"channels_version": "2", "access_token": token},
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            categories = data.get("data", []) or data
            if isinstance(categories, list):
                for cat in categories:
                    channels = cat.get("channels", [])
                    for ch in channels:
                        slug = str(ch.get("slug", "")).lower()
                        title = str(ch.get("title", "")).lower()
                        if "irbis" in slug or "ирбис" in title:
                            real_id = ch.get("id")
                            logger.info(f"Найден канал Irbis TV! Slug: {slug}, Real ID: {real_id}")
                            return int(real_id)
    except Exception as e:
        logger.warning(f"Не удалось получить ID через category_list: {e}")

    # Запасной вариант: если slug известен точно как 'irbis-tv', возвращаем жестко зашитый 
    # актуальный ID платформ24 для этого канала, если динамический поиск не сработал
    logger.info("Используем fallback ID для Irbis TV")
    return 142 # Или ваш найденный числовой id

def fetch_fresh_stream_url() -> str:
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "ru-RU,ru;q=0.9",
        "Referer": "https://app.birge.tv/"
    })

    try:
        # Шаг 1: Получаем гостевую сессию и токен
        logger.info("Авторизация на платформе Birge TV...")
        reg_response = session.post(f"{API_BASE}/v2/users", json={
            "username": "iptv_guest_user_auto",
            "password": "secure_guest_password_99",
            "is_guest": True
        }, timeout=10)

        token = None
        if reg_response.status_code in [200, 201]:
            data = reg_response.json()
            token = data.get("access_token") or data.get("data", {}).get("access_token")
        
        if not token:
            login_response = session.post(f"{API_BASE}/v2/auth/login", json={
                "login": "iptv_guest_user_auto",
                "password": "secure_guest_password_99"
            }, timeout=10)
            if login_response.status_code == 200:
                token = login_response.json().get("access_token")

        if not token:
            raise Exception("Auth token acquisition failed")

        # Шаг 2: Динамически определяем настоящий e.id канала
        channel_id = resolve_irbis_channel_id(session, token)

        logger.info(f"Запрос стрима для канала ID {channel_id} с Bearer-авторизацией...")

        # Шаг 3: Запрос потока по числовому ID с Bearer-токеном
        stream_headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json, text/plain, */*"
        }

        stream_response = session.get(
            f"{API_BASE}/v2/channels/{channel_id}/stream",
            headers=stream_headers,
            timeout=10
        )

        if stream_response.status_code != 200:
            logger.error(f"Ошибка стрима {stream_response.status_code}: {stream_response.text}")
            raise Exception("Stream endpoint returned error")

        stream_data = stream_response.json()
        
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
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
