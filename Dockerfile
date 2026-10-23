FROM python:3.12

WORKDIR /app
COPY . .
RUN pip install -r requirements.txt

EXPOSE 8080
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT:-8080} --workers 1 --threads 8 --timeout 60 app:app"]
