FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

# Keep dependencies in a reusable layer when application code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Run the service without root privileges.
RUN useradd --create-home appuser
COPY --chown=appuser:appuser app.py .
COPY --chown=appuser:appuser templates/ ./templates/
USER appuser

EXPOSE 8080
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT:-8080} --workers 1 --threads 8 --timeout 60 app:app"]
