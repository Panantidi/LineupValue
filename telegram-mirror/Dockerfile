FROM python:3.12-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# App
COPY bot.py .

# Session/state are persisted on a host volume
VOLUME ["/data"]

ENV SESSION_PATH=/data/session
ENV STATE_FILE=/data/state.json
ENV PYTHONUNBUFFERED=1

CMD ["python", "-u", "bot.py"]