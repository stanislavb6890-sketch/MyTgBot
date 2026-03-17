FROM python:3.12-slim

WORKDIR /app

# Устанавливаем системные зависимости
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Копируем зависимости
COPY requirements.txt .

# Устанавливаем Python зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код проекта
COPY . .

# Создаём venv для бота
RUN python -m venv /app/venv
ENV PATH="/app/venv/bin:$PATH"

# Порт для веб-сервера
EXPOSE 8080

# Запуск
CMD ["python", "bot/main.py"]
