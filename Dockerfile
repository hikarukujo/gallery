# SmartGallery (ComfyUI) container for AKS.
#
# Images are served from a FUSE-mounted S3 (QuObjects) bucket at /images — see the
# s3fs sidecar in platform-infra/apps/gallery/deployment.yaml. The SQLite index and
# thumbnails live on a LOCAL PVC at /cache (GALLERY_CACHE_DIR), never on the mount.
FROM python:3.12-slim

# Stamped by CI (build-and-deploy.yml) with the short commit SHA — parity with the other apps.
ARG BUILD_NUMBER=dev
LABEL org.opencontainers.image.revision=$BUILD_NUMBER

# System deps: ffmpeg/ffprobe (video workflow extraction) + libGL/glib for opencv.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# App code. config.py is generated from the env-driven example so no host paths bake in.
COPY smartgallery.py wsgi.py config_example.py ./
COPY templates ./templates
COPY static ./static
RUN cp config_example.py config.py

ENV GALLERY_SERVER_PORT=8189 \
    GALLERY_FFPROBE_MANUAL_PATH=/usr/bin/ffprobe

EXPOSE 8189

# 1 worker (shared caches + single SQLite writer), many threads for image I/O.
# No --preload: the background scan thread must live in the serving worker.
CMD ["gunicorn", "-w", "1", "--threads", "8", "-k", "gthread", \
     "-b", "0.0.0.0:8189", "--timeout", "300", "wsgi:app"]
