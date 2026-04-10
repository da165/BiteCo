#!/bin/bash
# user_data_postgres.sh — EC2-BD-Postgres (PostgreSQL central)
set -euo pipefail
exec > /var/log/user-data.log 2>&1

DB_PASS_SEG="${db_password_seguridad}"
DB_PASS_BD="${db_password_basedatos}"

echo "[$(date)] Iniciando setup EC2-BD-Postgres..."

apt-get update -y
apt-get install -y docker.io curl
systemctl enable docker
systemctl start docker

docker run -d \
  --name postgres_biteco \
  --restart unless-stopped \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD="$DB_PASS_SEG" \
  -p 5432:5432 \
  -v postgres_data:/var/lib/postgresql/data \
  postgres:15

echo "[$(date)] Esperando que PostgreSQL levante..."
for i in $(seq 1 15); do
  if docker exec postgres_biteco pg_isready -U postgres > /dev/null 2>&1; then
    echo "[$(date)] PostgreSQL listo en intento $i"
    break
  fi
  echo "  Intento $i/15 — esperando 10s..."
  sleep 10
done

# Crear las tres bases de datos necesarias
docker exec postgres_biteco psql -U postgres -c "CREATE DATABASE usuariosbitecodb;" 2>/dev/null || true
docker exec postgres_biteco psql -U postgres -c "CREATE DATABASE bitecodb;" 2>/dev/null || true
docker exec postgres_biteco psql -U postgres -c "CREATE DATABASE kong;" 2>/dev/null || true

echo "[$(date)] === EC2-BD-Postgres LISTA ===" | tee -a /var/log/user-data.log
