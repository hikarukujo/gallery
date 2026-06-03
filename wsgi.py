"""Gunicorn entrypoint for SmartGallery in containers.

Serves the Flask ``app`` and runs the (potentially slow, first-run) library scan in
a background thread so the web server becomes healthy immediately. Waits for the
image volume to be mounted before scanning, so we never index an empty mount, and
ensures the local cache dirs (SQLite + thumbnails, on the PVC) exist first.

Run with a single worker (shared in-memory caches + single SQLite writer) and
multiple threads, WITHOUT --preload (so the background thread lives in the worker
that actually serves, not a master that forks it away):

    gunicorn -w 1 --threads 8 -k gthread -b 0.0.0.0:8189 --timeout 300 wsgi:app
"""
import os
import threading
import time

from smartgallery import (
    app,
    initialize_gallery,
    BASE_OUTPUT_PATH,
    THUMBNAIL_CACHE_DIR,
    SQLITE_CACHE_DIR,
)


def _wait_for_mount(path, timeout=180):
    """Block until ``path`` looks mounted/populated, or timeout elapses."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if os.path.ismount(path) or (os.path.isdir(path) and os.listdir(path)):
                return True
        except OSError:
            pass
        print(f"INFO: waiting for image volume at {path} ...", flush=True)
        time.sleep(3)
    print(f"WARN: {path} not mounted after {timeout}s; scanning anyway.", flush=True)
    return False


def _bootstrap():
    # Cache dirs live on the local PVC (GALLERY_CACHE_DIR); make sure they exist.
    for d in (THUMBNAIL_CACHE_DIR, SQLITE_CACHE_DIR):
        os.makedirs(d, exist_ok=True)
    _wait_for_mount(BASE_OUTPUT_PATH)
    try:
        initialize_gallery()
        print("INFO: initial gallery scan complete.", flush=True)
    except Exception as e:  # never let a scan failure crash the server
        print(f"WARN: initial gallery scan failed: {e}", flush=True)


threading.Thread(target=_bootstrap, name="gallery-bootstrap", daemon=True).start()
