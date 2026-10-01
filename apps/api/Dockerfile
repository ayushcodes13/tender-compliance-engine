FROM python:3.12-slim AS base
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

FROM base AS deps
RUN pip install --upgrade pip && \
    pip install "uvicorn[standard]" && \
    uv tool install hatchling 2>/dev/null || true

FROM base AS runtime
COPY --from=deps /usr/local/lib/python*/site-packages /usr/local/lib/python*/site-packages
COPY pyproject.toml /app/pyproject.toml
COPY src/ /app/src/
RUN pip install -e ".[dev]" && \
    rm -rf /root/.cache/uv /app/src/*.egg-info

RUN groupadd -r app && useradd -r -g app app
USER app

CMD ["uvicorn", "tender_compliance_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
