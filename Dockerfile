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
# The "reflex" command is an executable script with a shebang to /app/.venv/bin/python, which itself is a symlink to
# /usr/local/bin/python. However, the ubuntu/python image we use at run-time does not have the Python binary at this
# path, but instead it resides at /usr/bin/python3. We therefore remove the symlink and create a new one to the correct
# Python binary.
RUN rm .venv/bin/python && ln -s /usr/bin/python3 .venv/bin/python

# Use the Ubuntu chiseled minimal Docker image for Python. In contrast to Google's "distroless" Python image, which
# offers no control over the Python version (other than "Python 3"), the Ubuntu image offers to at least control
# the minor version of Python (e.g. "3.12"). I'm not aware of free(!) minimal images that offer patch-level control.
FROM ubuntu/python:3.12-24.04 AS backend
ARG VIRTUAL_ENV
WORKDIR /app
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV TZ="UTC"
EXPOSE 8000
COPY --from=builder /app /app

# Needed until Reflex properly passes SIGTERM on backend.
STOPSIGNAL SIGKILL
# Instead of figuring out how Rockraft and Pebble services work (having tried and failed with a tutorial such as
# https://documentation.ubuntu.com/rockcraft/en/latest/how-to/rocks/convert-to-pebble-layer/), we simply copy a
# statically-linked shell from BusyBox and disable the default ["pebble", "enter"] entrypoint.
# Adding a shell (with no other tools) does not negatively affect the image security.
COPY --from=busybox:uclibc /bin/sh /bin/sh
ENTRYPOINT []
CMD reflex db migrate && exec reflex run --env prod --backend-only

FROM caddy:2.8.4 AS frontend
COPY --from=builder /app/.web/_static /srv
COPY Caddyfile /etc/caddy/Caddyfile