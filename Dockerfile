FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PROJECTS_ROOT_DIR=/srv/projects \
    STATE_DIR=/srv/state

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        git \
        bubblewrap \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/orchestrator

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

RUN useradd --create-home --shell /usr/sbin/nologin orchestrator \
    && mkdir -p /srv/projects /srv/state \
    && chown -R orchestrator:orchestrator /srv/orchestrator /srv/projects /srv/state \
    && chmod 700 /srv/state
USER orchestrator

VOLUME ["/srv/projects", "/srv/state"]

ENTRYPOINT ["python", "-m", "app"]
