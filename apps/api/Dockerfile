FROM python:3.12-slim
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

COPY pyproject.toml /app/pyproject.toml
COPY alembic.ini /app/alembic.ini
COPY alembic/ /app/alembic/
COPY src/ /app/src/

RUN pip install --upgrade pip && \
    pip install . && \
    rm -rf /root/.cache/pip

RUN groupadd --gid 10001 app && \
    useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin app && \
    mkdir -p /app/object-storage && \
    chown -R app:app /app/object-storage
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "tender_compliance_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
