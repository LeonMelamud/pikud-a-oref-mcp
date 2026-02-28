# SSE Relay Gateway - Dockerfile for Railway / standalone deployment
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd --create-home appuser && \
    mkdir -p /app/data && chown -R appuser:appuser /app
USER appuser

ENV PORT=8002

EXPOSE ${PORT}

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,os; urllib.request.urlopen(f'http://localhost:{os.getenv(\"PORT\",\"8002\")}/health')" || exit 1

CMD uvicorn src.api.sse_gateway:app --host 0.0.0.0 --port ${PORT}
