import os
import logging
import requests
from flask import Flask, redirect, abort

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("IPTV_Proxy")

app = Flask(__name__)
API_BASE = "https://birgetv.platform24.tv"

def fetch_fresh_stream_url(channel_id: int) -> str:
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "ru-RU,ru;q=0.9"
    })

    try:
        # Авторизация сессии
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

        # Запрос ссылки потока
        stream_response = session.get(
            f"{API_BASE}/v2/channels/{channel_id}/stream",
            params={"access_token": token},
            timeout=10
        )

        if stream_response.status_code != 200:
            raise Exception("Stream endpoint returned error")

        stream_data = stream_response.json()
        hls_url = stream_data.get("url") or stream_data.get("data", {}).get("url")
        
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
    return "IPTV Proxy Server is Running!"

@app.route("/stream/<int:channel_id>.m3u8")
def proxy_stream(channel_id):
    try:
        fresh_url = fetch_fresh_stream_url(channel_id)
        return redirect(fresh_url, code=302)
    except Exception:
        abort(502, description="Failed to fetch stream from Platform24")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
