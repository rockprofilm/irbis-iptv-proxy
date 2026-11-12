import os
import json
import logging
import subprocess
import sys
import time
from threading import Lock

import requests
from flask import Flask, redirect, abort

# ---------------------------------------------------------
# CONFIG
# ---------------------------------------------------------

VK_LIVE_URL = "https://live.vkvideo.ru/irbis_tv/"
CACHE_TTL = 30

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

logger = logging.getLogger("IPTV_Proxy")

app = Flask(__name__)

# Защита от одновременного запуска нескольких yt-dlp
stream_lock = Lock()

cached_url = None
cached_at = 0


# ---------------------------------------------------------
# HTTP SESSION
# ---------------------------------------------------------

session = requests.Session()

session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/157.0.0.0 Safari/537.36"
    ),
    "Referer": VK_LIVE_URL,
    "Accept": "*/*",
})


# ---------------------------------------------------------
# GET STREAM URL
# ---------------------------------------------------------

def get_vk_stream_url() -> str:
    """
    Получает актуальный playback URL через yt-dlp.

    yt-dlp обращается к странице VK Live и сам разбирает
    структуру плеера/источников.
    """

    global cached_url
    global cached_at

    now = time.time()

    # Используем URL из кэша недолго.
    # Это уменьшает количество обращений к VK.
    if cached_url and (now - cached_at < CACHE_TTL):
        logger.info("Using cached VK stream URL")
        return cached_url

    with stream_lock:

        # Повторная проверка после получения lock
        now = time.time()

        if cached_url and (now - cached_at < CACHE_TTL):
            return cached_url

        logger.info("Requesting fresh VK Live stream URL...")

        command = [
            sys.executable,
            "-m",
            "yt_dlp",

            # Только информация, без скачивания
            "--dump-single-json",

            # Не скачивать видео
            "--skip-download",

            # Не писать лишний вывод
            "--no-warnings",

            # JSON должен попасть в stdout
            "--quiet",

            # URL VK Live
            VK_LIVE_URL,
        ]

        try:
            result = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=30,
                check=False,
            )

        except subprocess.TimeoutExpired:
            logger.error("yt-dlp timeout")
            raise RuntimeError("yt-dlp timeout")

        if result.returncode != 0:
            logger.error(
                "yt-dlp failed: %s",
                result.stderr[-3000:]
            )
            raise RuntimeError(
                "yt-dlp failed to extract VK stream"
            )

        stdout = result.stdout.strip()

        if not stdout:
            raise RuntimeError(
                "yt-dlp returned empty output"
            )

        try:
            data = json.loads(stdout)

        except json.JSONDecodeError:
            logger.error(
                "Invalid JSON from yt-dlp: %s",
                stdout[:2000]
            )
            raise RuntimeError(
                "Invalid JSON returned by yt-dlp"
            )

        # -------------------------------------------------
        # Ищем прямой URL HLS
        # -------------------------------------------------

        formats = data.get("formats", [])

        hls_candidates = []

        for fmt in formats:
            url = fmt.get("url")

            if not url:
                continue

            protocol = str(fmt.get("protocol", "")).lower()
            manifest = str(fmt.get("manifest_url", "")).lower()

            if (
                "m3u8" in protocol
                or ".m3u8" in url.lower()
                or ".m3u8" in manifest
            ):
                hls_candidates.append(fmt)

        # Приоритет:
        # 1. HLS
        # 2. последний найденный URL
        if hls_candidates:

            # Предпочитаем максимально качественный поток
            hls_candidates.sort(
                key=lambda x: (
                    x.get("height") or 0,
                    x.get("tbr") or 0
                ),
                reverse=True
            )

            stream_url = hls_candidates[0].get("url")

        else:
            stream_url = None

            # Некоторые extractor'ы могут вернуть URL
            # непосредственно в поле url.
            if data.get("url"):
                possible = data["url"]

                if ".m3u8" in possible.lower():
                    stream_url = possible

        if not stream_url:
            logger.error(
                "No HLS URL found in yt-dlp response"
            )

            logger.error(
                "Extractor: %s",
                data.get("extractor")
            )

            logger.error(
                "Formats found: %s",
                len(formats)
            )

            raise RuntimeError(
                "VK Live HLS stream was not found"
            )

        # -------------------------------------------------
        # CACHE
        # -------------------------------------------------

        cached_url = stream_url
        cached_at = time.time()

        logger.info(
            "Fresh VK HLS URL obtained successfully"
        )

        logger.info(
            "Extractor: %s",
            data.get("extractor")
        )

        logger.info(
            "Title: %s",
            data.get("title")
        )

        return stream_url


# ---------------------------------------------------------
# ROUTES
# ---------------------------------------------------------

@app.route("/")
def index():
    return (
        "Irbis TV VK Live Proxy is running\n"
        "/stream/irbis.m3u8\n"
    )


@app.route("/health")
def health():
    return {
        "status": "ok",
        "service": "irbis-tv-vk-proxy"
    }


@app.route("/stream/irbis.m3u8")
def proxy_stream():

    try:

        stream_url = get_vk_stream_url()

        logger.info(
            "Redirecting IPTV client to VK HLS stream"
        )

        return redirect(
            stream_url,
            code=302
        )

    except Exception as e:

        logger.exception(
            "Failed to obtain VK stream: %s",
            e
        )

        abort(
            502,
            description=(
                "Failed to obtain live stream from VK Video"
            )
        )


# ---------------------------------------------------------
# START
# ---------------------------------------------------------

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            "10000"
        )
    )

    logger.info(
        "Starting Irbis TV proxy on port %s",
        port
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
