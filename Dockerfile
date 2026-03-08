FROM python:3.11-slim

LABEL description="Telegram bot for Sonarr/Radarr management"

WORKDIR /app

# Install dependencies first (separate layer — only re-runs if requirements.txt changes)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY butlarr/ ./butlarr/

# Pre-create data dirs so they are owned by root inside the image.
# The volume mount will overlay /app/data at runtime — Docker will
# preserve ownership of the host directory, so no permission issues.
RUN mkdir -p /app/data/session

COPY scripts/docker_entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["python3", "-m", "butlarr"]
