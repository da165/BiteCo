#!/bin/bash
# user_data_kong.sh — EC2-Kong (API Gateway + Konga)
set -euo pipefail
exec > /var/log/user-data.log 2>&1

REPO_URL="${repo_url}"
JWT_SECRET="${jwt_secret}"
IP_SEG="${ip_seguridad}"
IP_BD="${ip_basedatos}"
IP_AWS="${ip_aws}"

echo "[$(date)] Iniciando setup EC2-Kong..."

apt-get update -y
apt-get install -y docker.io docker-compose-plugin curl git
systemctl enable docker
systemctl start docker
usermod -aG docker ubuntu

cd /home/ubuntu
git clone "$REPO_URL" Bite_co
chown -R ubuntu:ubuntu /home/ubuntu/Bite_co

cd /home/ubuntu/Bite_co/Kong

# Levantar Kong (postgres + migrations + gateway + konga)
sudo -u ubuntu docker compose -f docker-compose.kong.yml up -d

echo "[$(date)] Esperando que Kong inicie (puede tardar hasta 3 minutos)..."
for i in $(seq 1 24); do
  if curl -sf http://localhost:8001/status > /dev/null 2>&1; then
    echo "[$(date)] Kong listo en intento $i"
    break
  fi
  echo "  Intento $i/24 — esperando 10s..."
  sleep 10
done

# FIX: Los puertos son los del HOST de cada EC2 (como los expone docker-compose)
#   Seguridad:  host:8000  (docker: web:8000)
#   BaseDatos:  host:8000  (docker: web:8000, mapeado en override)
#   AWS:        host:8000  (docker: web:8000, mapeado en override)
# Kong llama a estos servicios por IP:8000 (el contenedor web siempre escucha en 8000)
KONG_ADMIN=http://localhost:8001 \
IP_SEGURIDAD=$IP_SEG \
IP_BASE_DATOS=$IP_BD \
IP_AWS=$IP_AWS \
PORT_SEGURIDAD=8000 \
PORT_BASE_DATOS=8000 \
PORT_AWS=8000 \
JWT_SECRET=$JWT_SECRET \
  bash /home/ubuntu/Bite_co/Kong/setup_kong.sh

echo "[$(date)] === EC2-Kong LISTA ===" | tee -a /var/log/user-data.log
