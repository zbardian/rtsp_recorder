# RTSP Recorder

---

## 🇷🇴 Română

### Descriere

Recorder RTSP bazat pe `ffmpeg`, rulat in container Podman, cu segmentare video pe fisiere de durata fixa.
MediaMTX poate rula direct pe host si poate proxy-ui fluxul RTSP de la camera IP.
Containerul `rtsp_recorder` poate citi fie direct din camera, fie din MediaMTX. Recorderul trebuie sa foloseasca exact acelasi URL RTSP pe care il validezi cu succes in VLC.

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

- Citeste stream RTSP direct din camera sau via MediaMTX, in functie de `RTSP_URL`.
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
| `RTSP_USER`, `RTSP_PASS` | Optional; injecteaza autentificarea daca nu e deja in URL. Util cand proxy-ul RTSP cere auth, dar vrei sa pastrezi URL-ul curat |
| `OUTPUT_DIR` | Folder de salvare segmente |
| `SEGMENT_MINUTES` | Durata unui segment video |
| `SEGMENT_SECONDS` | Optional; daca e >0, suprascrie `SEGMENT_MINUTES` (util pentru debug rapid) |
| `MAX_DISK_USAGE` | Prag % utilizare disc; sterge fisiere vechi |
| `FFMPEG_LOGLEVEL` | Nivel log ffmpeg (`info`, `warning`) |
| `OUTPUT_EXT` | Format fisier: `mp4` pentru compatibilitate maxima sau `mkv` |
| `AUDIO_ENABLED` | `1`/`0` pentru activare/dezactivare inregistrare audio |
| `AUDIO_CODEC`, `AUDIO_BITRATE`, `AUDIO_FILTER` | Setari pentru codare audio (`aac` recomandat pentru compatibilitate maxima; `auto` sau `copy` doar daca stii sigur codec-ul sursa) |
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

La finalul fiecarui segment, logul afiseaza si daca fisierul salvat contine audio:

```text
Fisier salvat: video=1 audio=1 path=...
Audio in fisier: codec=aac sample_rate=... channels=...
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
- Daca VLC deschide `rtsp://host:port/path`, dar ffmpeg primeste `401`, seteaza separat `RTSP_USER` si `RTSP_PASS` in compose.

**Camera are audio in VLC, dar fisierul salvat nu are sunet**
- Testeaza in VLC exact acelasi `RTSP_URL` folosit de recorder, nu alt URL.
- Daca VLC are sunet pe URL-ul direct al camerei, dar nu pe `rtsp://127.0.0.1:8554/stream1`, atunci MediaMTX nu retransmite audio pe acel path.
- In acest caz, seteaza `RTSP_URL` pe URL-ul care are deja audio confirmat in VLC, de exemplu `rtsp://192.168.50.50:8554/stream1` sau direct pe camera `rtsp://user:parola@IP_CAMERA:554/stream1`.
- Pentru testul final de compatibilitate, foloseste `OUTPUT_EXT=mp4` si `AUDIO_CODEC=aac`.

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
MediaMTX can run directly on the host and proxy the RTSP stream from the IP camera.
The `rtsp_recorder` container can read either directly from the camera or through MediaMTX. The recorder should use the exact same RTSP URL that you have already validated in VLC.

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

- Reads RTSP stream either directly from the camera or through MediaMTX, depending on `RTSP_URL`.
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
| `RTSP_USER`, `RTSP_PASS` | Optional; injects credentials if not already in the URL. Useful when the RTSP proxy requires auth but you want to keep the URL clean |
| `OUTPUT_DIR` | Folder where segments are saved |
| `SEGMENT_MINUTES` | Duration of each video segment |
| `SEGMENT_SECONDS` | Optional; if >0, overrides `SEGMENT_MINUTES` (useful for quick debugging) |
| `MAX_DISK_USAGE` | Disk usage % threshold; deletes oldest files |
| `FFMPEG_LOGLEVEL` | ffmpeg log level (`info`, `warning`) |
| `OUTPUT_EXT` | Output format: `mp4` for maximum compatibility or `mkv` |
| `AUDIO_ENABLED` | `1`/`0` to enable/disable audio recording |
| `AUDIO_CODEC`, `AUDIO_BITRATE`, `AUDIO_FILTER` | Audio encoding settings (`aac` recommended for maximum compatibility; use `auto` or `copy` only if you know the source codec is safe) |
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
- If VLC opens `rtsp://host:port/path` but ffmpeg gets `401`, set `RTSP_USER` and `RTSP_PASS` separately in compose.

**Camera has audio in VLC, but the recorded file has no sound**
- Test the exact same `RTSP_URL` in VLC that the recorder uses.
- If VLC has sound on the direct camera URL but not on `rtsp://127.0.0.1:8554/stream1`, then MediaMTX is not forwarding audio on that path.
- In that case, set `RTSP_URL` to the URL already confirmed to have audio in VLC, for example `rtsp://192.168.50.50:8554/stream1`, or directly to the camera `rtsp://user:password@CAMERA_IP:554/stream1`.
- For the final compatibility test, use `OUTPUT_EXT=mp4` and `AUDIO_CODEC=aac`.

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
