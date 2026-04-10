#!/bin/bash
# user_data_aws.sh — EC2-AWS (microservicio AWS Cost Explorer)
set -euo pipefail
exec > /var/log/user-data.log 2>&1

REPO_URL="${repo_url}"
JWT_SECRET="${jwt_secret}"
MY_IP=$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 || echo "0.0.0.0")

echo "[$(date)] Iniciando setup EC2-AWS..."

apt-get update -y
apt-get install -y docker.io docker-compose-plugin curl git
systemctl enable docker
systemctl start docker
usermod -aG docker ubuntu

cd /home/ubuntu
git clone "$REPO_URL" Bite_co
chown -R ubuntu:ubuntu /home/ubuntu/Bite_co

cd /home/ubuntu/Bite_co/AWS

cat > docker-compose.override.yml << EOF
version: '3.8'
services:
  web:
    environment:
      - REDIS_URL=redis://redis:6379/2
      - JWT_SECRET=$JWT_SECRET
      - ALLOWED_HOSTS=0.0.0.0,localhost,127.0.0.1,$MY_IP
EOF

sudo -u ubuntu docker compose up -d --build

echo "[$(date)] Esperando que Django AWS levante..."
for i in $(seq 1 20); do
  if curl -sf http://localhost:8000/health/ > /dev/null 2>&1; then
    echo "[$(date)] Django AWS listo en intento $i"
    break
  fi
  echo "  Intento $i/20 — esperando 15s..."
  sleep 15
done

echo "[$(date)] === EC2-AWS LISTA ===" | tee -a /var/log/user-data.log
