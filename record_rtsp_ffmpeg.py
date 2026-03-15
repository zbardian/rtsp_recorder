#!/usr/bin/env python3
import os
import time
import psutil
import subprocess
import logging
import sys
import threading
from urllib.parse import quote, urlsplit, urlunsplit
from logging.handlers import RotatingFileHandler
from datetime import datetime

# ===== Config =====
RTSP_URL = os.environ.get("RTSP_URL", "rtsp://sd6csc3:12345678@192.168.50.129:554/stream1")
RTSP_USER = os.environ.get("RTSP_USER", "")
RTSP_PASS = os.environ.get("RTSP_PASS", "")
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "/mnt/storage1/rtsp_disk")
SEGMENT_MINUTES = int(os.environ.get("SEGMENT_MINUTES", 5))
MAX_DISK_USAGE = int(os.environ.get("MAX_DISK_USAGE", 90))
LOG_FILE = os.environ.get("LOG_FILE", "/var/log/rtsp_recorder.log")
FFMPEG_LOGLEVEL = os.environ.get("FFMPEG_LOGLEVEL", "warning")
RTSP_TIMEOUT_US = os.environ.get("RTSP_TIMEOUT_US", os.environ.get("RW_TIMEOUT_US", ""))
RTSP_TIMEOUT_OPTION = os.environ.get("RTSP_TIMEOUT_OPTION", "").lstrip("-")
OUTPUT_EXT = os.environ.get("OUTPUT_EXT", "mkv").lower().strip(".")

# ===== Logging rotativ =====
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
logger = logging.getLogger("RTSP_Recorder")
logger.setLevel(logging.INFO)
handler = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=5)
formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
handler.setFormatter(formatter)
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(formatter)
if not logger.handlers:
    logger.addHandler(handler)
    logger.addHandler(stream_handler)

# ===== Funcții utilitare =====
def is_mount_available(path):
    """Verifică dacă volumul extern este accesibil (compatibil Podman/Docker)."""
    return os.path.exists(path)

def get_disk_usage_percent(path):
    return psutil.disk_usage(path).percent

def delete_empty_dirs(path):
    """Șterge directoarele goale, evitând folderul de azi."""
    today = datetime.now().strftime("%Y-%m-%d")
    for root, dirs, files in os.walk(path, topdown=False):
        for d in dirs:
            if d == today: continue # Nu atingem folderul de azi
            full_path = os.path.join(root, d)
            if not os.listdir(full_path):
                logger.info(f"Șterg director gol: {full_path}")
                os.rmdir(full_path)

def delete_oldest_file_if_needed():
    try:
        usage = get_disk_usage_percent(OUTPUT_DIR)
        if usage >= MAX_DISK_USAGE:
            files = []
            for root, _, filenames in os.walk(OUTPUT_DIR):
                for f in filenames:
                    if f.endswith((".mp4", ".mkv")):
                        files.append(os.path.join(root, f))
            files.sort(key=os.path.getctime)
            if files:
                logger.warning(f"Limită disc atinsă ({usage}%). Șterg: {files[0]}")
                os.remove(files[0])
    except Exception as e:
        logger.error(f"Eroare la curățare disc: {e}")

def wait_for_mount():
    """Așteaptă până când discul este montat."""
    while not is_mount_available(OUTPUT_DIR):
        logger.warning(f"Discul extern {OUTPUT_DIR} nu este montat. Aștept 10 secunde...")
        time.sleep(10)
    logger.info(f"Discul {OUTPUT_DIR} este montat. Pornesc înregistrarea...")

def ensure_output_writable(path):
    """Verifică dacă path-ul de output este scriibil din container."""
    test_file = os.path.join(path, ".recorder_write_test")
    try:
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(test_file)
        return True
    except Exception as e:
        logger.error("Nu pot scrie în OUTPUT_DIR=%s (%s)", path, e)
        return False

def forward_ffmpeg_output(proc):
    """Trimite output-ul ffmpeg în logger pentru vizibilitate în docker logs."""
    if proc.stdout is None:
        return
    for line in proc.stdout:
        line = line.strip()
        if line:
            logger.info("ffmpeg: %s", line)

def build_rtsp_url(base_url, user, password):
    """Construiește URL RTSP cu autentificare când user/parolă sunt definite."""
    if not user:
        return base_url
    parsed = urlsplit(base_url)
    if "@" in parsed.netloc:
        return base_url
    host = parsed.hostname or ""
    port_part = f":{parsed.port}" if parsed.port else ""
    auth = quote(user, safe="")
    if password:
        auth = f"{auth}:{quote(password, safe='')}"
    netloc = f"{auth}@{host}{port_part}"
    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))

def sanitize_rtsp_url(url):
    """Ascunde parola din URL pentru log-uri."""
    parsed = urlsplit(url)
    if parsed.password is None:
        return url
    user = parsed.username or ""
    host = parsed.hostname or ""
    port_part = f":{parsed.port}" if parsed.port else ""
    netloc = f"{user}:***@{host}{port_part}"
    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))

EFFECTIVE_RTSP_URL = build_rtsp_url(RTSP_URL, RTSP_USER, RTSP_PASS)

# ===== Loop principal de captură =====
logger.info("Pornire serviciu înregistrare RTSP...")
logger.info(
    "Config: RTSP_URL=%s, OUTPUT_DIR=%s, SEGMENT_MINUTES=%s, MAX_DISK_USAGE=%s, FFMPEG_LOGLEVEL=%s, OUTPUT_EXT=%s, RTSP_TIMEOUT_OPTION=%s, RTSP_TIMEOUT_US=%s",
    sanitize_rtsp_url(EFFECTIVE_RTSP_URL),
    OUTPUT_DIR,
    SEGMENT_MINUTES,
    MAX_DISK_USAGE,
    FFMPEG_LOGLEVEL,
    OUTPUT_EXT,
    RTSP_TIMEOUT_OPTION,
    RTSP_TIMEOUT_US,
)

while True:
    wait_for_mount()

    today = datetime.now().strftime("%Y-%m-%d")
    day_dir = os.path.join(OUTPUT_DIR, today)
    os.makedirs(day_dir, exist_ok=True)
    if not ensure_output_writable(day_dir):
        time.sleep(10)
        continue

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    outfile = os.path.join(day_dir, f"{timestamp}.{OUTPUT_EXT}")

    # Am dezactivat audio (-an) pentru a evita eroarea pcm_alaw în container MP4
    ffmpeg_cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", FFMPEG_LOGLEVEL,
        "-rtsp_transport", "tcp",
    ]

    if RTSP_TIMEOUT_OPTION and RTSP_TIMEOUT_US:
        ffmpeg_cmd.extend([f"-{RTSP_TIMEOUT_OPTION}", RTSP_TIMEOUT_US])

    ffmpeg_cmd.extend([
        "-i", EFFECTIVE_RTSP_URL,
        "-c:v", "copy",
        "-an",
        "-t", str(SEGMENT_MINUTES * 60),
    ])

    if OUTPUT_EXT == "mp4":
        ffmpeg_cmd.extend(["-movflags", "+faststart"])
    else:
        ffmpeg_cmd.extend(["-f", "matroska"])

    ffmpeg_cmd.extend(["-y", outfile])

    logger.info(f"Încep captură segment: {outfile}")
    try:
        proc = subprocess.Popen(
            ffmpeg_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        forwarder = threading.Thread(target=forward_ffmpeg_output, args=(proc,), daemon=True)
        forwarder.start()

        while proc.poll() is None:
            if not is_mount_available(OUTPUT_DIR):
                logger.error("HDD deconectat! Opresc ffmpeg...")
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                break

            delete_oldest_file_if_needed()
            # Am dezactivat ștergerea directoarelor în timpul scrierii
            # delete_empty_dirs(OUTPUT_DIR)
            time.sleep(10)

        forwarder.join(timeout=2)
        if proc.returncode not in (0, None):
            logger.error(
                "ffmpeg s-a oprit cu eroare (returncode=%s). Verifică URL-ul RTSP și autentificarea.",
                proc.returncode,
            )

        logger.info(f"Segment terminat sau proces închis (status: {proc.returncode})")

    except Exception as e:
        logger.exception(f"Eroare fatală la rularea ffmpeg: {e}")

    time.sleep(5)
