#!/bin/bash
# user_data_pruebas.sh — EC2-Pruebas (JMeter + Locust)
set -euxo pipefail
exec > /var/log/user-data.log 2>&1

REPO_URL="${repo_url}"
IP_KONG="${ip_kong}"
IP_SEG="${ip_seguridad}"
IP_BD="${ip_basedatos}"
IP_AWS="${ip_aws}"

apt-get update -y
apt-get install -y docker.io docker-compose-plugin curl git python3-pip default-jre
systemctl enable docker
systemctl start docker
usermod -aG docker ubuntu

# ── Instalar Locust ─────────────────────────────────────────────
pip3 install locust requests tabulate --break-system-packages

# ── Instalar JMeter ─────────────────────────────────────────────
JMETER_VER="5.6.3"
wget -q "https://archive.apache.org/dist/jmeter/binaries/apache-jmeter-${JMETER_VER}.tgz" \
     -O /tmp/jmeter.tgz
tar -xzf /tmp/jmeter.tgz -C /opt/
mv /opt/apache-jmeter-${JMETER_VER} /opt/jmeter
ln -s /opt/jmeter/bin/jmeter /usr/local/bin/jmeter

# ── Clonar repositorio ──────────────────────────────────────────
cd /home/ubuntu
git clone "$REPO_URL" Bite_co

# ── Generar datos de prueba para Locust/JMeter ──────────────────
cd /home/ubuntu/Bite_co/Pruebas_Escalabilidad
python3 generar_datos_escalabilidad.py --usuarios 12000

# ── Crear archivo de configuración con las IPs reales ───────────
cat > /home/ubuntu/Bite_co/Pruebas_Escalabilidad/config_ips.env << EOF
KONG_HOST=http://$IP_KONG:8080
IP_SEGURIDAD=$IP_SEG
IP_BASEDATOS=$IP_BD
IP_AWS=$IP_AWS
IP_KONG=$IP_KONG
EOF

# ── Script de inicio rápido para el equipo ──────────────────────
cat > /home/ubuntu/correr_pruebas.sh << 'SCRIPT'
#!/bin/bash
source /home/ubuntu/Bite_co/Pruebas_Escalabilidad/config_ips.env
cd /home/ubuntu/Bite_co/Pruebas_Escalabilidad

echo "Iniciando pruebas contra Kong: $KONG_HOST"
echo ""
echo "Opciones:"
echo "  1) Locust UI web   (abre navegador en :8089)"
echo "  2) Locust headless nominal  (5000 usuarios, 10 min)"
echo "  3) Locust headless pico     (12000 usuarios, 5 min)"
echo "  4) JMeter headless latencia"
echo ""
read -p "Selecciona (1-4): " op

case $op in
  1) locust -f locustfile.py --host $KONG_HOST ;;
  2) locust -f locustfile.py --host $KONG_HOST --users 5000 --spawn-rate 84 \
       --run-time 600s --headless --html results/nominal.html ;;
  3) locust -f locustfile.py --host $KONG_HOST --users 12000 --spawn-rate 200 \
       --run-time 300s --headless --html results/pico.html ;;
  4) jmeter -n -t ../Seguridad/Test/plan_prueba_experimento.jmx \
       -l results/jmeter.jtl -e -o results/jmeter_report/ \
       -JHOST_ORQUESTADOR=$IP_BASEDATOS -JPUERTO_ORQUESTADOR=8000 ;;
esac
SCRIPT

chmod +x /home/ubuntu/correr_pruebas.sh
chown -R ubuntu:ubuntu /home/ubuntu/Bite_co /home/ubuntu/correr_pruebas.sh

echo "=== EC2-Pruebas lista ===" >> /var/log/user-data.log
