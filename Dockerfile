# One container for production: the built website + API + background worker.

# ---- website
FROM node:22-slim AS web
RUN npm install -g pnpm@10.34.5
WORKDIR /srv/apps/web
COPY apps/web/package.json apps/web/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY apps/web ./
# invite-only: no "Create account" page
ENV VITE_SIGNUP_OPEN=false
RUN pnpm build

# ---- API + worker
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.9.26 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1
WORKDIR /srv/apps/api
COPY apps/api/pyproject.toml apps/api/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY apps/api ./
COPY seed /srv/seed
COPY --from=web /srv/apps/web/dist /srv/apps/web/dist

RUN useradd --create-home --uid 1000 app && mkdir -p /srv/data && chown app /srv/data
USER app

ENV ENV=prod \
    HOST=0.0.0.0 \
    PORT=8000 \
    RUN_WORKER=true \
    WEB_DIST=/srv/apps/web/dist \
    STORAGE_ROOT=/srv/data \
    LOG_JSON=true
# 512 MB on the free plan: stop glibc keeping a separate memory pool per thread
ENV MALLOC_ARENA_MAX=2
EXPOSE 8000
# database migrations run on every start (a no-op when already up to date)
CMD ["sh", "-c", "alembic upgrade head && exec python -m app.main"]
