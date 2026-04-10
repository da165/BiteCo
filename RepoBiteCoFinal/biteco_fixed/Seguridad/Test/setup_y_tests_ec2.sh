#!/bin/bash
# =============================================================================
# setup_y_tests_ec2.sh
# Script para instalar dependencias y correr todos los tests en EC2 Ubuntu 24.04
#
# Uso:
#   chmod +x setup_y_tests_ec2.sh
#   ./setup_y_tests_ec2.sh [secuencial|unitarios|latencia|todo]
#
# Ejemplo:
#   ./setup_y_tests_ec2.sh todo
# =============================================================================

set -e  # Salir si cualquier comando falla
MODO=${1:-todo}

echo "======================================================"
echo "  Bite.Co - Runner de Tests - Sprint 2"
echo "  Modo: $MODO"
echo "======================================================"

# ─────────────────────────────────────────────
# PARTE 1: Instalar dependencias (solo primera vez)
# ─────────────────────────────────────────────
instalar_dependencias() {
    echo ""
    echo "📦 Instalando dependencias del sistema..."
    sudo apt-get update -q
    sudo apt-get install -y python3-pip python3-venv default-jre

    echo "📦 Instalando JMeter..."
    JMETER_VERSION="5.6.3"
    if [ ! -d "/opt/jmeter" ]; then
        wget -q "https://archive.apache.org/dist/jmeter/binaries/apache-jmeter-${JMETER_VERSION}.tgz" -O /tmp/jmeter.tgz
        sudo tar -xzf /tmp/jmeter.tgz -C /opt/
        sudo mv /opt/apache-jmeter-${JMETER_VERSION} /opt/jmeter
        echo "✅ JMeter instalado en /opt/jmeter"
    else
        echo "✅ JMeter ya instalado"
    fi

    echo "📦 Instalando dependencias Python para tests de latencia..."
    pip3 install --quiet requests statistics tabulate
}

# ─────────────────────────────────────────────
# PARTE 2: Tests Unitarios Django
# ─────────────────────────────────────────────
correr_tests_unitarios() {
    echo ""
    echo "🧪 Corriendo Tests Unitarios..."
    echo "------------------------------------------------------"

    # Microservicio Seguridad
    echo ""
    echo "▶ Tests: Microservicio Seguridad"
    cd ~/Seguridad
    pip3 install -q -r requirements.txt
    python manage.py test seguridad --verbosity=2 2>&1
    RESULT_SEG=$?

    # Microservicio AWS
    echo ""
    echo "▶ Tests: Microservicio AWS"
    cd ~/AWS
    pip3 install -q -r requirements.txt
    python manage.py test AWS_Consulta --verbosity=2 2>&1
    RESULT_AWS=$?

    # Microservicio Base_Datos (Orquestador)
    echo ""
    echo "▶ Tests: Microservicio Base_Datos (Orquestador)"
    cd ~/Base_Datos
    pip3 install -q -r requirements.txt
    python manage.py test BD_ManejoCostos --verbosity=2 2>&1
    RESULT_BD=$?

    echo ""
    echo "======================================================="
    echo "RESUMEN TESTS UNITARIOS:"
    [ $RESULT_SEG -eq 0 ] && echo "  ✅ Seguridad: PASS" || echo "  ❌ Seguridad: FAIL"
    [ $RESULT_AWS -eq 0 ] && echo "  ✅ AWS: PASS" || echo "  ❌ AWS: FAIL"
    [ $RESULT_BD -eq 0 ]  && echo "  ✅ Base_Datos: PASS" || echo "  ❌ Base_Datos: FAIL"
    echo "======================================================="
}

# ─────────────────────────────────────────────
# PARTE 3: Tests de Latencia con Python
# ─────────────────────────────────────────────
correr_tests_latencia_python() {
    echo ""
    echo "⏱️  Corriendo Tests de Latencia (Python)..."
    echo "------------------------------------------------------"
    echo "  Asegúrate de que los microservicios estén corriendo:"
    echo "  - Base_Datos Orquestador en puerto 8002"
    echo ""

    # Ajusta la IP si los servicios están en otra máquina EC2
    HOST_ORQUESTADOR=${HOST_ORQUESTADOR:-"http://localhost:8002"}
    HOST_BROKER=${HOST_BROKER:-"http://localhost:8003"}

    python3 ~/tests/latencia/test_latencia_asr.py \
        --host-secuencial "$HOST_ORQUESTADOR" \
        --host-broker "$HOST_BROKER" \
        --usuarios 1 10 50 100 200 500

    echo ""
    echo "💾 Resultados en: resultados_latencia.csv"
}

# ─────────────────────────────────────────────
# PARTE 4: Tests de Carga con JMeter (headless)
# ─────────────────────────────────────────────
correr_tests_jmeter() {
    echo ""
    echo "🔨 Corriendo Tests JMeter en modo headless..."
    echo "------------------------------------------------------"

    JMETER_HOME="/opt/jmeter"
    PLAN="~/tests/latencia/plan_prueba_experimento.jmx"
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    RESULTADO_JTL="resultados_jmeter_${TIMESTAMP}.jtl"
    REPORTE_HTML="reporte_html_${TIMESTAMP}"

    ${JMETER_HOME}/bin/jmeter \
        -n \
        -t ${PLAN} \
        -l ${RESULTADO_JTL} \
        -e \
        -o ${REPORTE_HTML} \
        -JHOST_ORQUESTADOR=${HOST_ORQUESTADOR:-"localhost"} \
        -JPUERTO_ORQUESTADOR=8002

    echo ""
    echo "✅ JMeter completado"
    echo "   Resultados JTL: ${RESULTADO_JTL}"
    echo "   Reporte HTML: ${REPORTE_HTML}/index.html"
    echo ""
    echo "💡 Para ver el reporte HTML, copia la carpeta a tu máquina local:"
    echo "   scp -r ubuntu@<EC2-IP>:~/${REPORTE_HTML} ./reporte_jmeter/"
}

# ─────────────────────────────────────────────
# Dispatcher
# ─────────────────────────────────────────────
case "$MODO" in
    "instalar")
        instalar_dependencias
        ;;
    "unitarios")
        correr_tests_unitarios
        ;;
    "latencia")
        correr_tests_latencia_python
        ;;
    "jmeter")
        correr_tests_jmeter
        ;;
    "todo")
        instalar_dependencias
        correr_tests_unitarios
        correr_tests_latencia_python
        correr_tests_jmeter
        ;;
    *)
        echo "Uso: $0 [instalar|unitarios|latencia|jmeter|todo]"
        exit 1
        ;;
esac

echo ""
echo "🏁 Listo."
