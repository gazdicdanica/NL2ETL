FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN apt-get update && apt-get install -y docker.io && rm -rf /var/lib/apt/lists/*

COPY . .
CMD ["fastapi", "dev", "main.py", "--host", "0.0.0.0", "--port", "8000"]
