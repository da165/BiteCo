#!/bin/bash
# user_data_seguridad.sh — EC2-Seguridad
# Se ejecuta automáticamente la primera vez que la instancia arranca.
set -euo pipefail
exec > /var/log/user-data.log 2>&1

REPO_URL="${repo_url}"
JWT_SECRET="${jwt_secret}"
DB_PASSWORD="${db_password}"
IP_BD="${ip_bd_postgres}"
# IP pública de esta instancia (se resuelve en tiempo de ejecución)
MY_IP=$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 || echo "0.0.0.0")

echo "[$(date)] Iniciando setup EC2-Seguridad..."

# ── Sistema ──────────────────────────────────────────────────
apt-get update -y
apt-get install -y docker.io docker-compose-plugin curl git
systemctl enable docker
systemctl start docker
newgrp docker << 'NEWGRP'
NEWGRP
usermod -aG docker ubuntu

# ── Clonar repositorio ───────────────────────────────────────
cd /home/ubuntu
git clone "$REPO_URL" Bite_co
chown -R ubuntu:ubuntu /home/ubuntu/Bite_co

# ── docker-compose.override.yml ─────────────────────────────
# Apunta a EC2-BD-Postgres (externa) en lugar de la BD local del compose
cd /home/ubuntu/Bite_co/Seguridad
cat > docker-compose.override.yml << EOF
version: '3.8'
services:
  db:
    profiles: ["disabled"]
  web:
    environment:
      - DATABASE_NAME=usuariosbitecodb
      - DATABASE_USER=postgres
      - DATABASE_PASSWORD=$DB_PASSWORD
      - DATABASE_HOST=$IP_BD
      - DATABASE_PORT=5432
      - REDIS_URL=redis://redis:6379/1
      - JWT_SECRET=$JWT_SECRET
      - ALLOWED_HOSTS=0.0.0.0,localhost,127.0.0.1,$MY_IP
EOF

# ── Construir y levantar (como ubuntu para tener acceso al socket Docker) ──
sudo -u ubuntu docker compose up -d --build

echo "[$(date)] Contenedores levantados. Esperando que Django termine de iniciar..."

# ── FIX: esperar con retry hasta que el healthcheck responda ─
for i in $(seq 1 20); do
  if curl -sf http://localhost:8000/health/ > /dev/null 2>&1; then
    echo "[$(date)] Django listo en intento $i"
    break
  fi
  echo "  Intento $i/20 — Django aún no responde, esperando 15s..."
  sleep 15
done

# ── Migrate y seed de usuarios ───────────────────────────────
sudo -u ubuntu docker compose exec -T web python manage.py migrate --noinput
sudo -u ubuntu docker compose exec -T web python manage.py seed_usuarios --cantidad 100

echo "[$(date)] === EC2-Seguridad LISTA ===" | tee -a /var/log/user-data.log
