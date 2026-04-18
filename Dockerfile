# 白羊 server · macOS dev / Linux prod
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install -e .

COPY server ./server
COPY shared ./shared
COPY pipeline ./pipeline
COPY config ./config
COPY db ./db
COPY scripts ./scripts

RUN mkdir -p data logs

EXPOSE 8327

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8327/v1/health',timeout=3).status==200 else 1)"

CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8327"]
