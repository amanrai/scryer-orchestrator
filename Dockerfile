FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends git tmux bash \
    && rm -rf /var/lib/apt/lists/* \
    && git config --global user.name "Scryer Orchestrator" \
    && git config --global user.email "orchestrator@scryer.local"

WORKDIR /app

COPY requirements.txt ./
COPY app ./app

RUN pip install --no-cache-dir -r requirements.txt

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8101"]
