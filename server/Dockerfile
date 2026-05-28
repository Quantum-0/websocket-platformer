# Используем легкую версию Python
FROM python:3.11-slim

# Ставим рабочую директорию внутри контейнера
WORKDIR /app

# Устанавливаем библиотеку для работы с веб-сокетами
RUN pip install --no-cache-dir websockets

# Копируем наш код сервера
COPY server.py .

# Запускаем сервер
CMD ["python", "server.py"]
