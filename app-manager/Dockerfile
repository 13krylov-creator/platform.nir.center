# App Manager - Python FastAPI service
FROM python:3.11-slim

WORKDIR /app

# Установка docker CLI для nginx reload
RUN apt-get update && apt-get install -y --no-install-recommends \
    docker.io \
    && rm -rf /var/lib/apt/lists/*

# Копируем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код
COPY main.py .

# Переменные окружения
ENV APPS_JSON_PATH=/data/apps.json
ENV NGINX_CONF_DIR=/nginx-conf
ENV NGINX_CONTAINER=iam-nginx

# Открываем порт
EXPOSE 8000

# Запуск
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
