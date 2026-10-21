# Une image par service, construites depuis le même Dockerfile (cibles etl, api, web).
#   docker build --target api -t scoring-api .

# --- Base commune : Python + uv ---
FROM python:3.13-slim AS base
COPY --from=ghcr.io/astral-sh/uv:0.13.4 /uv /bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/app/.venv PATH="/app/.venv/bin:$PATH"
# Fichiers du workspace nécessaires à la résolution des dépendances
COPY pyproject.toml uv.lock .python-version ./
COPY pkg/pyproject.toml pkg/pyproject.toml
COPY services/api/pyproject.toml services/api/pyproject.toml
COPY web/pyproject.toml web/pyproject.toml


# --- ETL : package métier + migrations (sert aussi au service "migrate") ---
FROM base AS etl
RUN uv sync --frozen --no-dev --package scoring-ifrs9 --no-install-workspace
COPY pkg pkg
RUN uv sync --frozen --no-dev --package scoring-ifrs9
COPY alembic.ini ./
COPY migrations migrations
CMD ["scoring-ifrs9", "run-all"]


# --- API : FastAPI + package métier ---
FROM base AS api
RUN uv sync --frozen --no-dev --package scoring-api --no-install-workspace
COPY pkg pkg
COPY services/api services/api
RUN uv sync --frozen --no-dev --package scoring-api
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]


# --- Web : Streamlit, ne parle qu'à l'API ---
FROM base AS web
RUN uv sync --frozen --no-dev --package scoring-web
COPY web web
EXPOSE 8501
CMD ["streamlit", "run", "web/streamlit_app.py", "--server.port=8501", "--server.address=0.0.0.0"]
