FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libglib2.0-0 fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY model_requirements.txt .
RUN pip install --no-cache-dir -r model_requirements.txt
COPY app ./app
COPY web ./web
COPY rules.json ./rules.json
ENV PYTHONUNBUFFERED=1 DATA_DIR=/data RULES_PATH=/srv/rules.json
