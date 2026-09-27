# ads-runner-agent backend image.
# Build from the repo root:  docker build -t ads-runner-agent .
# Run:  docker run --env-file backend/.env -p 8007:8007 ads-runner-agent
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ ./backend/
WORKDIR /app/backend

ENV PORT=8007
EXPOSE 8007

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8007')+'/health',timeout=4)"

CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port ${PORT:-8007}"]
