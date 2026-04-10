#!/bin/bash
# user_data_basedatos.sh — EC2-BaseDatos (Orquestador)
set -euo pipefail
exec > /var/log/user-data.log 2>&1

REPO_URL="${repo_url}"
JWT_SECRET="${jwt_secret}"
DB_PASSWORD="${db_password}"
IP_BD="${ip_bd_postgres}"
IP_AWS="${ip_aws_service}"
MY_IP=$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 || echo "0.0.0.0")

echo "[$(date)] Iniciando setup EC2-BaseDatos..."

apt-get update -y
apt-get install -y docker.io docker-compose-plugin curl git
systemctl enable docker
systemctl start docker
usermod -aG docker ubuntu

cd /home/ubuntu
git clone "$REPO_URL" Bite_co
chown -R ubuntu:ubuntu /home/ubuntu/Bite_co

cd /home/ubuntu/Bite_co/Base_Datos

# FIX: La URL del microservicio AWS usa el puerto 8000 interno del contenedor
# (docker-compose.yaml de AWS mapea host:8001 -> container:8000,
#  pero desde otra EC2 se accede por IP:8001 que es el puerto del host)
sed -i "s|http://aws-service:8000/api/fetch-costs/|http://$IP_AWS:8001/api/aws/costos/|g" \
    BD_ManejoCostos/views.py

cat > docker-compose.override.yml << EOF
version: '3.8'
services:
  db:
    profiles: ["disabled"]
  web:
    environment:
      - DATABASE_NAME=bitecodb
      - DATABASE_USER=postgres
      - DATABASE_PASSWORD=$DB_PASSWORD
      - DATABASE_HOST=$IP_BD
      - DATABASE_PORT=5432
      - REDIS_URL=redis://redis:6379/3
      - JWT_SECRET=$JWT_SECRET
      - ALLOWED_HOSTS=0.0.0.0,localhost,127.0.0.1,$MY_IP
EOF

sudo -u ubuntu docker compose up -d --build

echo "[$(date)] Esperando que Django BaseDatos levante..."
for i in $(seq 1 20); do
  if curl -sf http://localhost:8000/health/ > /dev/null 2>&1; then
    echo "[$(date)] Django BaseDatos listo en intento $i"
    break
  fi
  echo "  Intento $i/20 — esperando 15s..."
  sleep 15
done

sudo -u ubuntu docker compose exec -T web python manage.py migrate --noinput

echo "[$(date)] === EC2-BaseDatos LISTA ===" | tee -a /var/log/user-data.log
