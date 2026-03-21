# RTSP Recorder

---

## 🇷🇴 Română

### Descriere

Recorder RTSP bazat pe `ffmpeg`, rulat in container Podman, cu segmentare video pe fisiere de durata fixa.
MediaMTX ruleaza direct pe host si captureaza fluxul RTSP de la camera IP, restreameaza local pe `localhost:8554`.
Containerul `rtsp_recorder` se conecteaza la MediaMTX via `localhost` si salveaza segmente video pe disc.

### Arhitectura

```
Camera IP (flux RTSP)
        |
        v
  MediaMTX (proxy RTSP)
  ruleaza direct pe host
  localhost:8554/stream1
        |
        v
  rtsp_recorder (container, network_mode: host)
  citeste stream de la MediaMTX via localhost
        |
        v
  /mnt/storage1/rtsp_disk/YYYY-MM-DD/HHmmss.mkv
```

### Ce face

- Citeste stream RTSP de la MediaMTX via `localhost`.
- Salveaza segmente video + audio pe disc (implicit 5 minute per segment).
- Creeaza subfoldere pe zile (`YYYY-MM-DD`).
- Sterge automat cel mai vechi fisier cand se depaseste pragul de utilizare disc.
- Logheaza in fisier si in stdout (vizibil cu `podman logs`).

### Structura fisiere

- `record_rtsp_ffmpeg.py` - scriptul principal de inregistrare.
- `docker-compose.yml` - configuratie container si variabile de mediu.
- `Dockerfile` - imagine Python + ffmpeg.
- `container-rtsp_recorder.service` - unitate systemd pentru pornire la boot.

### Configurare (docker-compose.yml)

| Variabila | Descriere |
|---|---|
| `RTSP_URL` | URL stream RTSP (include user:parola@host:port/path) |
| `RTSP_USER`, `RTSP_PASS` | Optional; injecteaza autentificarea daca nu e deja in URL |
| `OUTPUT_DIR` | Folder de salvare segmente |
| `SEGMENT_MINUTES` | Durata unui segment video |
| `MAX_DISK_USAGE` | Prag % utilizare disc; sterge fisiere vechi |
| `FFMPEG_LOGLEVEL` | Nivel log ffmpeg (`info`, `warning`) |
| `OUTPUT_EXT` | Format fisier: `mkv` (recomandat) sau `mp4` |
| `AUDIO_ENABLED` | `1`/`0` pentru activare/dezactivare inregistrare audio |
| `AUDIO_CODEC`, `AUDIO_BITRATE`, `AUDIO_FILTER` | Setari pentru codare audio (`copy` recomandat; sau `aac` + bitrate + filtru) |
| `RTSP_TIMEOUT_OPTION`, `RTSP_TIMEOUT_US` | Lasa goale daca ffmpeg nu suporta optiunea |

### Pornire manuala

```bash
podman compose up -d --build --force-recreate
podman ps
podman logs -f rtsp_recorder
```

### Verificare inregistrare

```bash
# Urmareste logul live
podman logs -f rtsp_recorder

# Verifica fisierele generate azi
ls -lah /mnt/storage1/rtsp_disk/$(date +%F)
```

### Pornire automata dupa reboot (systemd)

```bash
sudo cp /opt/parking/rtsp_recorder/container-rtsp_recorder.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now container-rtsp_recorder.service
sudo systemctl status container-rtsp_recorder.service
```

Daca schimbi configuratia compose sau imaginea, recreeaza containerul:

```bash
podman compose down
podman compose up -d --build --force-recreate
```

### Troubleshooting

**`401 Unauthorized`**
- Verifica `RTSP_URL`, `RTSP_USER`, `RTSP_PASS`.
- Verifica `readUser`/`readPass` in configuratia MediaMTX pentru path-ul `stream1`.

**`Unrecognized option 'stimeout'` sau `rw_timeout`**
- Lasa goale in compose: `RTSP_TIMEOUT_OPTION=` si `RTSP_TIMEOUT_US=`

**Nu poate scrie fisiere**
- Verifica mount-ul volumului in compose.
- Verifica permisiunile pe `/mnt/storage1/rtsp_disk`.
- In log apare: `Nu pot scrie in OUTPUT_DIR=...`

**Containerul nu apare**
```bash
podman ps -a --filter name=rtsp_recorder
podman inspect rtsp_recorder --format "Name={{.Name}} Status={{.State.Status}}"
```

**Mesajul `Emulate Docker CLI using podman`**
```bash
sudo touch /etc/containers/nodocker
```

---

## 🇬🇧 English

### Description

RTSP recorder based on `ffmpeg`, running in a Podman container, saving video in fixed-duration segments.
MediaMTX runs directly on the host, capturing the RTSP stream from the IP camera and restreaming it locally on `localhost:8554`.
The `rtsp_recorder` container connects to MediaMTX via `localhost` and saves video segments to disk.

### Architecture

```
IP Camera (RTSP stream)
        |
        v
  MediaMTX (RTSP proxy)
  runs directly on host
  localhost:8554/stream1
        |
        v
  rtsp_recorder (container, network_mode: host)
  reads stream from MediaMTX via localhost
        |
        v
  /mnt/storage1/rtsp_disk/YYYY-MM-DD/HHmmss.mkv
```

### What it does

- Reads RTSP stream from MediaMTX via `localhost`.
- Saves video + audio segments to disk (default 5 minutes per segment).
- Creates daily subfolders (`YYYY-MM-DD`).
- Automatically deletes the oldest file when disk usage exceeds the threshold.
- Logs to file and stdout (visible via `podman logs`).

### File structure

- `record_rtsp_ffmpeg.py` - main recording script.
- `docker-compose.yml` - container configuration and environment variables.
- `Dockerfile` - Python + ffmpeg image.
- `container-rtsp_recorder.service` - systemd unit for auto-start on boot.

### Configuration (docker-compose.yml)

| Variable | Description |
|---|---|
| `RTSP_URL` | RTSP stream URL (include user:password@host:port/path) |
| `RTSP_USER`, `RTSP_PASS` | Optional; injects credentials if not already in URL |
| `OUTPUT_DIR` | Folder where segments are saved |
| `SEGMENT_MINUTES` | Duration of each video segment |
| `MAX_DISK_USAGE` | Disk usage % threshold; deletes oldest files |
| `FFMPEG_LOGLEVEL` | ffmpeg log level (`info`, `warning`) |
| `OUTPUT_EXT` | Output format: `mkv` (recommended) or `mp4` |
| `AUDIO_ENABLED` | `1`/`0` to enable/disable audio recording |
| `AUDIO_CODEC`, `AUDIO_BITRATE`, `AUDIO_FILTER` | Audio encoding settings (`copy` recommended; or `aac` + bitrate + filter) |
| `RTSP_TIMEOUT_OPTION`, `RTSP_TIMEOUT_US` | Leave empty if ffmpeg does not support the option |

### Manual start

```bash
podman compose up -d --build --force-recreate
podman ps
podman logs -f rtsp_recorder
```

### Verify recordings

```bash
# Follow live log
podman logs -f rtsp_recorder

# Check today's recorded files
ls -lah /mnt/storage1/rtsp_disk/$(date +%F)
```

### Auto-start on reboot (systemd)

```bash
sudo cp /opt/parking/rtsp_recorder/container-rtsp_recorder.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now container-rtsp_recorder.service
sudo systemctl status container-rtsp_recorder.service
```

If you change compose config or rebuild the image, recreate the container first:

```bash
podman compose down
podman compose up -d --build --force-recreate
```

### Troubleshooting

**`401 Unauthorized`**
- Check `RTSP_URL`, `RTSP_USER`, `RTSP_PASS`.
- Check `readUser`/`readPass` in MediaMTX config for the `stream1` path.

**`Unrecognized option 'stimeout'` or `rw_timeout`**
- Leave empty in compose: `RTSP_TIMEOUT_OPTION=` and `RTSP_TIMEOUT_US=`

**Cannot write files**
- Check volume mount in compose.
- Check permissions on `/mnt/storage1/rtsp_disk`.
- Log shows: `Nu pot scrie in OUTPUT_DIR=...`

**Container not found**
```bash
podman ps -a --filter name=rtsp_recorder
podman inspect rtsp_recorder --format "Name={{.Name}} Status={{.State.Status}}"
```

**`Emulate Docker CLI using podman` message**
```bash
sudo touch /etc/containers/nodocker
```
