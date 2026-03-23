FROM python:3.11-slim

# Prevent Python from buffering stdout/stderr (Docker-friendly logging)
ENV PYTHONUNBUFFERED=1

# Create non-root user + install gosu for entrypoint user-switching
RUN groupadd -r tracker && useradd -r -g tracker -m tracker \
    && apt-get update && apt-get install -y --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/

# Create data directory and set ownership
RUN mkdir -p /app/data && chown -R tracker:tracker /app /app/data

# Entrypoint runs as root, fixes volume perms, then drops to tracker
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["python", "-m", "app.main"]
