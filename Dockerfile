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
ENV API_URL='http://${BACKEND_DOMAIN_AND_PORT}'
# Note: API_URL is only used during build-time, not during run-time
RUN reflex export --frontend-only --no-zip
# Patch the BACKEND_PROTOCOL_SECURE_SUFFIX env var into the js bundle, verifying its structure / content
RUN python patch_js_bundle.py

# TODO migrate to chiseled ubuntu-based image
FROM python:3.12-slim AS backend
ARG VIRTUAL_ENV
WORKDIR /app
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
ENV PYTHONUNBUFFERED=1
EXPOSE 8000
COPY --from=builder /app /app

# COPY --from=builder /usr/bin/unzip /usr/bin/unzip
# RUN reflex init

# Needed until Reflex properly passes SIGTERM on backend.
STOPSIGNAL SIGKILL

CMD reflex db migrate && exec reflex run --env prod --backend-only

FROM nginxinc/nginx-unprivileged:1.27.1-alpine-slim AS frontend
# To make the backend API URL configurable at container start-time, we use the envsubst mechanism of the nginx image,
# see https://hub.docker.com/_/nginx in section "Using environment variables in nginx configuration"
# The admin who runs this container needs to set BACKEND_DOMAIN_AND_PORT (and optionally set BACKEND_PROTOCOL_SECURE_SUFFIX='s')
# at start-time.
ENV BACKEND_DOMAIN_AND_PORT='overwrite-me:1234'
# Overwrite with "s" if you want to use HTTPS/WSS
ENV BACKEND_PROTOCOL_SECURE_SUFFIX=

COPY --from=builder --chown=nginx /app/.web/_static /usr/share/nginx/html

ENV NGINX_ENVSUBST_TEMPLATE_DIR=/usr/share/nginx/html/_next/static/chunks/pages
ENV NGINX_ENVSUBST_OUTPUT_DIR=$NGINX_ENVSUBST_TEMPLATE_DIR
