FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY edc_translation ./edc_translation
COPY schemas ./schemas

RUN pip install --no-cache-dir ".[postgres,kafka]" \
    && useradd --create-home --uid 10001 appuser \
    && mkdir -p /data/jobs \
    && chown -R appuser:appuser /app /data

USER appuser

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/readyz', timeout=3)"

CMD ["uvicorn", "edc_translation.api:app", "--host", "0.0.0.0", "--port", "8080"]
