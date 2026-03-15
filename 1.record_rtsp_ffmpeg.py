#!/usr/bin/env python3
import os
import time
import psutil
import subprocess
import logging
import shutil
from logging.handlers import RotatingFileHandler
from datetime import datetime

# ===== Config =====
RTSP_URL = os.environ.get("RTSP_URL", "rtsp://sd6csc3:12345678@192.168.50.129:554/stream1")
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "/mnt/storage1/rtsp_disk")
SEGMENT_MINUTES = int(os.environ.get("SEGMENT_MINUTES", 5))
MAX_DISK_USAGE = int(os.environ.get("MAX_DISK_USAGE", 90))
LOG_FILE = os.environ.get("LOG_FILE", "/var/log/rtsp_recorder.log")

# ===== Logging rotativ =====
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
logger = logging.getLogger("RTSP_Recorder")
logger.setLevel(logging.INFO)
handler = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=5)
formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
handler.setFormatter(formatter)
logger.addHandler(handler)

# ===== Funcții utilitare =====
def is_mount_available(path):
    """Verifică dacă volumul extern este montat."""
#    return os.path.ismount(path)
#    return os.path.isdir(path)
    return os.path.exists(path)
def get_disk_usage_percent(path):
    return psutil.disk_usage(path).percent

def delete_empty_dirs(path):
    """Șterge toate directoarele goale dintr-un path."""
    for root, dirs, files in os.walk(path, topdown=False):
        for d in dirs:
            full_path = os.path.join(root, d)
            # Dacă directorul e gol, îl șterge
            if not os.listdir(full_path):
                logger.info(f"Șterg director gol: {full_path}")
                os.rmdir(full_path)

def delete_oldest_file_if_needed():
    usage = get_disk_usage_percent(OUTPUT_DIR)
    if usage >= MAX_DISK_USAGE:
        files = []
        for root, _, filenames in os.walk(OUTPUT_DIR):
            for f in filenames:
                if f.endswith(".mp4"):
                    files.append(os.path.join(root, f))
        files.sort(key=os.path.getctime)
        if files:
            logger.warning(f"Șterg fișier vechi: {files[0]}")
            os.remove(files[0])


def wait_for_mount():
    """Așteaptă până când discul este montat."""
    while not is_mount_available(OUTPUT_DIR):
        logger.warning(f"Discul extern {OUTPUT_DIR} nu este montat. Aștept 10 secunde...")
        time.sleep(10)
    logger.info(f"Discul {OUTPUT_DIR} este montat. Pornesc înregistrarea...")

# ===== Loop principal de captură =====
logger.info("Pornire serviciu înregistrare RTSP...")

while True:
    wait_for_mount()  # Așteaptă montarea HDD-ului

    today = datetime.now().strftime("%Y-%m-%d")
    day_dir = os.path.join(OUTPUT_DIR, today)
    os.makedirs(day_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    outfile = os.path.join(day_dir, f"{timestamp}.mp4")
#  "-an",  # dezactivează complet audio
    ffmpeg_cmd = [
        "ffmpeg",
        "-rtsp_transport", "tcp",
        "-i", RTSP_URL,
        "-c:v", "copy",
        "-c:a", "aac",
        "-t", str(SEGMENT_MINUTES * 60),
        "-movflags", "+faststart",
        "-y",
        outfile
    ]

    logger.info(f"Încep captură segment: {outfile}")
    try:
        proc = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)

        while proc.poll() is None:
            # dacă HDD-ul s-a deconectat în timpul înregistrării → oprește ffmpeg
            if not is_mount_available(OUTPUT_DIR):
                logger.error("HDD-ul a fost deconectat! Oprire înregistrare curentă...")
                proc.terminate()
                proc.wait(timeout=5)
                break

            delete_oldest_file_if_needed()
            delete_empty_dirs(OUTPUT_DIR)
            time.sleep(5)

        logger.info(f"Segment terminat: {outfile}")

    except Exception as e:
        logger.exception(f"Eroare la rularea ffmpeg: {e}")

    # Mică pauză între segmente (sau până revine discul)
    time.sleep(2)
