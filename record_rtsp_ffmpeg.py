#!/usr/bin/env python3
import os
import time
import psutil
import subprocess
import logging
import sys
import threading
import json
from urllib.parse import quote, urlsplit, urlunsplit
from logging.handlers import RotatingFileHandler
from datetime import datetime

# ===== Config =====
RTSP_URL = os.environ.get("RTSP_URL", "rtsp://sd6csc3:12345678@192.168.50.129:554/stream1")
RTSP_USER = os.environ.get("RTSP_USER", "")
RTSP_PASS = os.environ.get("RTSP_PASS", "")
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "/mnt/storage1/rtsp_disk")
SEGMENT_MINUTES = int(os.environ.get("SEGMENT_MINUTES", 5))
SEGMENT_SECONDS = int(os.environ.get("SEGMENT_SECONDS", "0"))
MAX_DISK_USAGE = int(os.environ.get("MAX_DISK_USAGE", 90))
LOG_FILE = os.environ.get("LOG_FILE", "/var/log/rtsp_recorder.log")
FFMPEG_LOGLEVEL = os.environ.get("FFMPEG_LOGLEVEL", "warning")
RTSP_TIMEOUT_US = os.environ.get("RTSP_TIMEOUT_US", os.environ.get("RW_TIMEOUT_US", ""))
RTSP_TIMEOUT_OPTION = os.environ.get("RTSP_TIMEOUT_OPTION", "").lstrip("-")
OUTPUT_EXT = os.environ.get("OUTPUT_EXT", "mkv").lower().strip(".")
AUDIO_ENABLED = os.environ.get("AUDIO_ENABLED", "1").strip().lower() not in ("0", "false", "no", "off")
AUDIO_CODEC = os.environ.get("AUDIO_CODEC", "auto").strip().lower() or "auto"
AUDIO_BITRATE = os.environ.get("AUDIO_BITRATE", "64k").strip()
AUDIO_FILTER = os.environ.get("AUDIO_FILTER", "aresample=async=1").strip()


def normalize_audio_bitrate(bitrate, sample_rate, channels):
    """Cap AAC bitrate on very low sample-rate streams to avoid encoder clamp warnings."""
    try:
        value = int((bitrate or "").lower().rstrip("k"))
    except Exception:
        value = 64

    sr = int(sample_rate) if sample_rate else 8000
    ch = int(channels) if channels else 1

    if sr <= 8000 and ch <= 1:
        value = min(value, 48)
    elif sr <= 16000:
        value = min(value, 64)

    return f"{max(value, 24)}k"

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
    return os.path.exists(path)

def get_disk_usage_percent(path):
    return psutil.disk_usage(path).percent

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
    while not is_mount_available(OUTPUT_DIR):
        logger.warning(f"Discul extern {OUTPUT_DIR} nu este montat. Aștept 10 secunde...")
        time.sleep(10)
    logger.info(f"Discul {OUTPUT_DIR} este montat. Pornesc înregistrarea...")

def ensure_output_writable(path):
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
    if proc.stdout is None:
        return
    for line in proc.stdout:
        line = line.strip()
        if line:
            logger.info("ffmpeg: %s", line)

def probe_rtsp_streams(url):
    cmd = [
        "ffprobe",
        "-v", "error",
        "-print_format", "json",
        "-show_streams",
        "-rtsp_transport", "tcp",
        url,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        if result.returncode != 0:
            logger.warning("ffprobe a eșuat (code=%s): %s", result.returncode, (result.stderr or "").strip())
            return None
        payload = json.loads(result.stdout or "{}")
        return payload.get("streams", [])
    except Exception as e:
        logger.warning("Nu am putut rula ffprobe pentru diagnostic audio: %s", e)
        return None


def probe_media_file(path):
    cmd = [
        "ffprobe",
        "-v", "error",
        "-print_format", "json",
        "-show_streams",
        path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        if result.returncode != 0:
            logger.warning("ffprobe fișier a eșuat pentru %s (code=%s): %s", path, result.returncode, (result.stderr or "").strip())
            return None
        payload = json.loads(result.stdout or "{}")
        return payload.get("streams", [])
    except Exception as e:
        logger.warning("Nu am putut verifica fișierul salvat %s: %s", path, e)
        return None


def log_output_file_streams(path):
    streams = probe_media_file(path)
    if streams is None:
        return

    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
    video_streams = [s for s in streams if s.get("codec_type") == "video"]
    logger.info("Fișier salvat: video=%s audio=%s path=%s", len(video_streams), len(audio_streams), path)
    if audio_streams:
        audio_stream = audio_streams[0]
        logger.info(
            "Audio în fișier: codec=%s sample_rate=%s channels=%s",
            audio_stream.get("codec_name", "?"),
            audio_stream.get("sample_rate", "?"),
            audio_stream.get("channels", "?"),
        )
    else:
        logger.warning("Fișierul salvat nu conține stream audio: %s", path)

def build_rtsp_url(base_url, user, password):
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
    parsed = urlsplit(url)
    if parsed.password is None:
        return url
    user = parsed.username or ""
    host = parsed.hostname or ""
    port_part = f":{parsed.port}" if parsed.port else ""
    netloc = f"{user}:***@{host}{port_part}"
    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))

EFFECTIVE_RTSP_URL = build_rtsp_url(RTSP_URL, RTSP_USER, RTSP_PASS)


def resolve_audio_settings(streams):
    if not AUDIO_ENABLED:
        return {"enabled": False, "codec": None, "sample_rate": None, "channels": None, "filter": None}

    audio_streams = [s for s in (streams or []) if s.get("codec_type") == "audio"]
    if not audio_streams:
        return {"enabled": True, "codec": None, "sample_rate": None, "channels": None, "filter": None}

    audio_stream = audio_streams[0]
    source_codec = (audio_stream.get("codec_name") or "").lower()
    sample_rate = audio_stream.get("sample_rate")
    channels = audio_stream.get("channels")

    resolved_codec = AUDIO_CODEC
    if AUDIO_CODEC == "auto":
        codecs_needing_transcode = {"pcm_alaw", "pcm_mulaw", "adpcm_g722", "adpcm_g726"}
        resolved_codec = "aac" if source_codec in codecs_needing_transcode or OUTPUT_EXT == "mp4" else "copy"

    resolved_filter = AUDIO_FILTER if resolved_codec != "copy" else ""
    return {
        "enabled": True,
        "codec": resolved_codec,
        "sample_rate": sample_rate,
        "channels": channels,
        "filter": resolved_filter,
    }

streams = probe_rtsp_streams(EFFECTIVE_RTSP_URL)
audio_settings = resolve_audio_settings(streams)
if streams is not None:
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
    video_streams = [s for s in streams if s.get("codec_type") == "video"]
    logger.info("Diagnostic stream: video=%s audio=%s", len(video_streams), len(audio_streams))
    if audio_streams:
        a0 = audio_streams[0]
        logger.info(
            "Audio detectat: codec=%s sample_rate=%s channels=%s",
            a0.get("codec_name", "?"),
            a0.get("sample_rate", "?"),
            a0.get("channels", "?"),
        )
        logger.info(
            "Audio output: codec=%s filter=%s",
            audio_settings.get("codec") or "none",
            audio_settings.get("filter") or "none",
        )
    elif AUDIO_ENABLED:
        logger.warning("Nu există stream audio în sursa RTSP. Verifică sursa/MediaMTX/path-ul (ex: stream principal).")

# ===== Loop principal de captură =====
logger.info("Pornire serviciu înregistrare RTSP...")

SEGMENT_DURATION_SECONDS = SEGMENT_SECONDS if SEGMENT_SECONDS > 0 else SEGMENT_MINUTES * 60
logger.info("Durată segment activă: %s secunde", SEGMENT_DURATION_SECONDS)

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

    # Comandă FFMPEG corectată pentru Tapo C310
    ffmpeg_cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", FFMPEG_LOGLEVEL,
        "-use_wallclock_as_timestamps", "1",
        "-rtsp_transport", "tcp",
    ]

    if RTSP_TIMEOUT_OPTION and RTSP_TIMEOUT_US:
        ffmpeg_cmd.extend([f"-{RTSP_TIMEOUT_OPTION}", RTSP_TIMEOUT_US])

    ffmpeg_cmd.extend([
        "-i", EFFECTIVE_RTSP_URL,
        "-map", "0:v:0",             # Mapare explicită video
        "-c:v", "copy",              # Stream copy pentru video
        "-t", str(SEGMENT_DURATION_SECONDS),
    ])

    if AUDIO_ENABLED:
        # Fix robust: include explicit audio map + AAC transcode to avoid silent output with RTSP pcm_alaw.
        ffmpeg_cmd.extend(["-map", "0:a:0?"])
        ffmpeg_cmd.extend(["-c:a", "aac"])
        target_bitrate = normalize_audio_bitrate(
            AUDIO_BITRATE or "64k",
            audio_settings.get("sample_rate"),
            audio_settings.get("channels"),
        )
        ffmpeg_cmd.extend(["-b:a", target_bitrate])
        if audio_settings.get("sample_rate"):
            ffmpeg_cmd.extend(["-ar", str(audio_settings["sample_rate"])])
        else:
            ffmpeg_cmd.extend(["-ar", "8000"])
        if audio_settings.get("channels"):
            ffmpeg_cmd.extend(["-ac", str(audio_settings["channels"])])
        else:
            ffmpeg_cmd.extend(["-ac", "1"])
        ffmpeg_cmd.extend(["-af", AUDIO_FILTER or "aresample=async=1:first_pts=0"])
    else:
        ffmpeg_cmd.append("-an")

    if OUTPUT_EXT == "mp4":
        ffmpeg_cmd.extend(["-movflags", "+faststart"])
    else:
        ffmpeg_cmd.extend(["-f", "matroska"])

    ffmpeg_cmd.extend(["-y", outfile])

    display_cmd = [sanitize_rtsp_url(x) if x == EFFECTIVE_RTSP_URL else x for x in ffmpeg_cmd]
    logger.info("Comandă ffmpeg: %s", " ".join(display_cmd))

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
                break
            delete_oldest_file_if_needed()
            time.sleep(10)

        proc.wait()
        forwarder.join(timeout=2)
        
        if proc.returncode not in (0, None):
            logger.error("ffmpeg s-a oprit cu eroare (returncode=%s).", proc.returncode)
        elif os.path.exists(outfile):
            log_output_file_streams(outfile)
        
        logger.info(f"Segment terminat (status: {proc.returncode})")

    except Exception as e:
        logger.exception(f"Eroare la rularea ffmpeg: {e}")

    time.sleep(5)
