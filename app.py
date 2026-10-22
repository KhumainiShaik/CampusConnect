"""CampusConnect: a tiny college technical-fest events portal."""
from flask import Flask, jsonify, render_template

app = Flask(__name__)

EVENTS = [
    {"id": "hack-2026", "title": "Campus Hackathon", "category": "Hackathon", "date": "24 October 2026", "venue": "Innovation Lab"},
    {"id": "cloud-workshop", "title": "Cloud & DevOps Workshop", "category": "Workshop", "date": "23 October 2026", "venue": "Seminar Hall A"},
    {"id": "code-sprint", "title": "Code Sprint", "category": "Coding contest", "date": "29 October 2026", "venue": "Computer Centre"},
    {"id": "robo-arena", "title": "Robo Arena", "category": "Robotics", "date": "31 October 2026", "venue": "Main Auditorium"},
]


@app.get("/")
def index():
    return render_template("index.html", events=EVENTS)


@app.get("/health")
def health():
    return jsonify(status="ok")


@app.get("/api/events")
def api_events():
    return jsonify(EVENTS)
    