# CampusConnect

A small Flask app that lists campus events.

## Run locally

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m flask --app app run --port 8080
```

Open <http://127.0.0.1:8080>. The app also provides `/health` and `/api/events`.

## Run with Docker

```sh
docker build -t campusconnect .
docker run --rm -p 8080:8080 campusconnect
```

Then open <http://127.0.0.1:8080>.
