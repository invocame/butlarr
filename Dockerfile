FROM python:3.11-slim

LABEL maintainer="butlarr"
LABEL description="Telegram bot for Sonarr/Radarr management"

# Create non-root user
RUN groupadd -r butlarr && useradd -r -g butlarr butlarr

WORKDIR /app

# Install dependencies first (separate layer — only re-runs if requirements.txt changes)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY butlarr/ ./butlarr/

# Data directory for session storage
RUN mkdir -p /app/data/session \
 && chown -R butlarr:butlarr /app/data

# Entrypoint
COPY scripts/docker_entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

USER butlarr

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["python3", "-m", "butlarr"]
