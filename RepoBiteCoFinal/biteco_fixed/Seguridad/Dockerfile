FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# FIX: curl necesario para el healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app/

EXPOSE 8000

# FIX: CMD usa Gunicorn (se sobreescribe en docker-compose para migrations primero)
CMD ["gunicorn", "biteco_server.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "9", "--threads", "4"]
