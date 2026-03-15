# Folosim imagine oficială Python cu ffmpeg
FROM python:3.12-slim

# Install ffmpeg și psutil
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    pip install psutil && \
    rm -rf /var/lib/apt/lists/*

# Setăm workdir
WORKDIR /app

# Copiem scriptul în container
COPY record_rtsp_ffmpeg.py /app/record_rtsp_ffmpeg.py

# Expunem port doar dacă vrei web (opțional)
# EXPOSE 5020

# Comanda default
CMD ["python", "/app/record_rtsp_ffmpeg.py"]
