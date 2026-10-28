"""CampusConnect: a tiny college technical-fest events portal."""
from io import BytesIO
import os
from pathlib import Path

from flask import Flask, abort, jsonify, render_template, send_file
from google.api_core.exceptions import GoogleAPIError
from google.auth.exceptions import GoogleAuthError
from google.cloud import storage

app = Flask(__name__)

ASSET_DIRECTORY = Path(__file__).parent / "sample-assets"
PUBLIC_FILES = {"announcement.txt": "text/plain", "poster.svg": "image/svg+xml"}


def read_resource(name):
    """Use bundled files locally, or the configured private bucket on Cloud Run."""
    bucket_name = os.environ.get("STORAGE_BUCKET", "").strip()
    if not bucket_name:
        return (ASSET_DIRECTORY / name).read_bytes()
    # Application Default Credentials use the attached Cloud Run service account.
    client = storage.Client()
    return client.bucket(bucket_name).blob(name).download_as_bytes(timeout=10, retry=None)


EVENTS = [
    {"id": "hack-2026", "title": "Campus Hackathon", "category": "Hackathon", "date": "24 October 2026", "venue": "Innovation Lab"},
    {"id": "cloud-workshop", "title": "Cloud & DevOps Workshop", "category": "Workshop", "date": "23 October 2026", "venue": "Seminar Hall A"},
    {"id": "code-sprint", "title": "Code Sprint", "category": "Coding contest", "date": "29 October 2026", "venue": "Computer Centre"},
    {"id": "robo-arena", "title": "Robo Arena", "category": "Robotics", "date": "31 October 2026", "venue": "Main Auditorium"},
]


@app.get("/")
def index():
    try:
        announcement = read_resource("announcement.txt").decode("utf-8")
    except (GoogleAPIError, GoogleAuthError, OSError, UnicodeError):
        app.logger.exception("Unable to load the campus announcement")
        announcement = "The campus announcement is temporarily unavailable."
    return render_template("index.html", events=EVENTS, announcement=announcement)


@app.get("/resources/<name>")
def resource(name):
    # Only these two intentionally public assets can be read through the app.
    if name not in PUBLIC_FILES:
        abort(404)
    try:
        contents = read_resource(name)
    except (GoogleAPIError, GoogleAuthError, OSError):
        app.logger.exception("Unable to load resource %s", name)
        return "This campus resource is temporarily unavailable.\n", 503
    response = send_file(BytesIO(contents), mimetype=PUBLIC_FILES[name], download_name=name)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.get("/health")
def health():
    return jsonify(status="ok")


@app.get("/api/events")
def api_events():
    return jsonify(EVENTS)
