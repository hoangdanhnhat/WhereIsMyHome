FROM python:3.11-slim

# Prevent Python from buffering stdout/stderr (Docker-friendly logging)
ENV PYTHONUNBUFFERED=1

# Create non-root user
RUN groupadd -r tracker && useradd -r -g tracker -m tracker

WORKDIR /app

# Install dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/

# Create data directory and set ownership
RUN mkdir -p /app/data && chown -R tracker:tracker /app /app/data

USER tracker

CMD ["python", "-m", "app.main"]
