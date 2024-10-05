ARG VIRTUAL_ENV=/app/.venv
FROM python:3.12 AS builder
ARG VIRTUAL_ENV
WORKDIR /app

RUN python -m venv $VIRTUAL_ENV
COPY requirements.txt .
RUN $VIRTUAL_ENV/bin/pip install --no-cache-dir -r requirements.txt
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
COPY . .
# Note: "reflex export" implicitly runs "reflex init", which downloads Node.js
# Note: we also remove large folders inside the .web folder which we need in neither the frontend nor backend
RUN reflex export --frontend-only --no-zip && rm -rf .web/node_modules .web/.next

# TODO migrate to chiseled ubuntu-based image
FROM python:3.12-slim AS backend
ARG VIRTUAL_ENV
WORKDIR /app
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
ENV PYTHONUNBUFFERED=1
EXPOSE 8000
COPY --from=builder /app /app

# Needed until Reflex properly passes SIGTERM on backend.
STOPSIGNAL SIGKILL

CMD reflex db migrate && exec reflex run --env prod --backend-only

FROM caddy:2.8.4 AS frontend
COPY --from=builder /app/.web/_static /srv
COPY Caddyfile /etc/caddy/Caddyfile
