# RTSP Recorder

Recorder RTSP bazat pe `ffmpeg`, rulat in container, cu segmentare video pe fisiere de durata fixa.

## Ce face

- Citeste stream RTSP de la MediaMTX/camera.
- Salveaza segmente video in folderul de output (implicit 5 minute).
- Creeaza subfoldere pe zile (`YYYY-MM-DD`).
- Sterge automat cel mai vechi fisier cand se depaseste pragul de utilizare disc.
- Logheaza in fisier si in stdout (vizibil in logs container).

## Structura

- `record_rtsp_ffmpeg.py` - scriptul principal de inregistrare.
- `docker-compose.yml` - configuratie container si variabile de mediu.
- `Dockerfile` - imagine Python + ffmpeg.
- `container-rtsp_recorder.service` - unitate systemd (Podman-generated) pentru pornire la boot.

## Configurare (docker-compose.yml)

Variabile importante:

- `RTSP_URL` - URL stream RTSP (poate include user/parola in URL).
- `RTSP_USER`, `RTSP_PASS` - optional; folosite pentru injectarea autentificarii daca `RTSP_URL` nu are deja `user:pass@`.
- `OUTPUT_DIR` - path de salvare in container.
- `SEGMENT_MINUTES` - durata unui segment.
- `MAX_DISK_USAGE` - prag procentual de disk usage.
- `FFMPEG_LOGLEVEL` - nivel log ffmpeg (`info`, `warning`, etc).
- `OUTPUT_EXT` - `mkv` (recomandat) sau `mp4`.
- `RTSP_TIMEOUT_OPTION`, `RTSP_TIMEOUT_US` - optional; lasate goale daca build-ul ffmpeg nu suporta optiunile.

Exemplu URL autenticat:

`rtsp://user:parola@192.168.50.50:8554/stream1`

## Pornire manuala

### Cu Podman Compose

```bash
podman compose up -d --build --force-recreate
podman ps
podman logs -f rtsp_recorder
```

### Cu Docker Compose (daca folosesti docker CLI)

```bash
docker compose up -d --build --force-recreate
docker ps
docker logs -f rtsp_recorder
```

## Verificare inregistrare

1. Verifica logul:

```bash
podman logs -f rtsp_recorder
```

2. Verifica fisierele generate:

```bash
ls -lah /mnt/storage1/rtsp_disk/$(date +%F)
```

3. Deschide segmentul in VLC.

## Pornire automata dupa reboot (systemd + podman start)

Fisierul `container-rtsp_recorder.service` porneste containerul existent `rtsp_recorder`:

```bash
sudo cp /opt/parking/rtsp_recorder/container-rtsp_recorder.service /etc/systemd/system/container-rtsp_recorder.service
sudo systemctl daemon-reload
sudo systemctl enable --now container-rtsp_recorder.service
sudo systemctl status container-rtsp_recorder.service
```

Daca schimbi configuratia compose sau imaginea, recreeaza containerul inainte:

```bash
podman compose down
podman compose up -d --build --force-recreate
```

## Troubleshooting rapid

### 1) `401 Unauthorized`

- Verifica autentificarea din `RTSP_URL` sau `RTSP_USER`/`RTSP_PASS`.
- Verifica `readUser/readPass` (si eventual `readIPs`) in configuratia MediaMTX pentru path-ul `stream1`.

### 2) `Unrecognized option 'rw_timeout'` sau `Unrecognized option 'stimeout'`

- Lasa goale in `docker-compose.yml`:
  - `RTSP_TIMEOUT_OPTION=`
  - `RTSP_TIMEOUT_US=`

### 3) Nu poate scrie fisiere

- Verifica mount-ul host -> container pentru `OUTPUT_DIR`.
- Verifica permisiunile pe `/mnt/storage1/rtsp_disk`.
- In logs apare explicit: `Nu pot scrie in OUTPUT_DIR=...`.

### 4) Nu apare containerul `rtsp_recorder`

```bash
podman ps -a --filter name=rtsp_recorder
podman inspect rtsp_recorder --format "Name={{.Name}} Status={{.State.Status}}"
```

## Note

- Mesajul `Emulate Docker CLI using podman` este informativ.
- Pentru a-l ascunde:

```bash
sudo touch /etc/containers/nodocker
```
