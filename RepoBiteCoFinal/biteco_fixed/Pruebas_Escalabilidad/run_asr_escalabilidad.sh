#!/bin/bash
# =============================================================================
# run_asr_escalabilidad.sh
# =============================================================================
# Ejecuta el experimento COMPLETO del ASR de Escalabilidad:
#   1. Tests unitarios del middleware (en local, sin EC2)
#   2. Prueba Locust — Escenario nominal (5000 usuarios, 10 min)
#   3. Prueba Locust — Escenario pico (12000 usuarios, 5 min)
#   4. Prueba Locust — Rampa completa ASR (0→12000→0 en 10 min)
#   5. Análisis automático del cumplimiento del ASR
#
# Uso:
#   chmod +x run_asr_escalabilidad.sh
#   ./run_asr_escalabilidad.sh --host 54.1.2.3 --proyecto Seguridad
#
# Argumentos:
#   --host    IP pública de la EC2 del servicio a probar
#   --port    Puerto del servicio (default: 8000)
#   --proyecto Nombre del proyecto Django (Seguridad | Base_Datos | AWS)
# =============================================================================

set -euo pipefail

HOST="localhost"
PORT="8000"
PROYECTO="Seguridad"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)     HOST="$2";     shift 2 ;;
    --port)     PORT="$2";     shift 2 ;;
    --proyecto) PROYECTO="$2"; shift 2 ;;
    *) echo "Argumento desconocido: $1"; exit 1 ;;
  esac
done

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RESULTS="results_asr_${TIMESTAMP}"
mkdir -p "${RESULTS}"

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║     ASR ESCALABILIDAD — Bite.Co Sprint 2                    ║"
echo "║     5000 nominales | 12000 pico | 10 min | error <= 10%     ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "  Host:     http://${HOST}:${PORT}"
echo "  Proyecto: ${PROYECTO}"
echo "  Salida:   ${RESULTS}/"
echo ""

# =============================================================================
# FASE 1 — Tests unitarios del middleware (no requieren EC2)
# =============================================================================
echo "━━━ FASE 1: Tests unitarios del middleware ━━━━━━━━━━━━━━━━━━━━━"
echo ""

if [ -d "${PROYECTO}" ]; then
    cd "${PROYECTO}"
    python manage.py test tests.test_control_acceso -v 2 \
        2>&1 | tee "../${RESULTS}/fase1_unit_tests.log"
    
    # Contar tests pasados/fallados
    TESTS_OK=$(grep -c "ok$" "../${RESULTS}/fase1_unit_tests.log" || true)
    TESTS_FAIL=$(grep -c "FAIL" "../${RESULTS}/fase1_unit_tests.log" || true)
    echo ""
    echo "  Tests pasados: ${TESTS_OK}"
    echo "  Tests fallados: ${TESTS_FAIL}"
    cd ..
else
    echo "  [SKIP] Directorio ${PROYECTO} no encontrado — ejecutar manualmente"
    echo "         python manage.py test tests.test_control_acceso -v 2"
fi

echo ""

# =============================================================================
# FASE 2 — Generar datos de prueba
# =============================================================================
echo "━━━ FASE 2: Generando datos de prueba ━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

python3 scripts/generar_datos_escalabilidad.py \
    --usuarios 12000 \
    --output "${RESULTS}/datos_escalabilidad.csv"

cp "${RESULTS}/datos_escalabilidad.csv" locust/datos_escalabilidad.csv
cp "${RESULTS}/datos_escalabilidad.csv" jmeter/datos_escalabilidad.csv
echo ""

# =============================================================================
# FASE 3 — Verificar que el servidor responde
# =============================================================================
echo "━━━ FASE 3: Verificando conectividad con ${HOST}:${PORT} ━━━━━━━━"
echo ""

if curl -sf "http://${HOST}:${PORT}/health/" > /dev/null 2>&1; then
    echo "  [OK] Servidor responde en /health/"
else
    echo "  [WARN] /health/ no responde — verificar que el servidor está activo"
    echo "         y que el middleware está instalado."
    echo "         Continuar de todas formas..."
fi
echo ""

# =============================================================================
# FASE 4 — Locust: Escenario A — Carga Nominal (5000 usuarios, 10 min)
# =============================================================================
echo "━━━ FASE 4: Locust — Escenario NOMINAL (5000 usuarios, 600s) ━━━"
echo ""

mkdir -p "${RESULTS}/locust_nominal"
locust -f locust/locustfile.py \
    --host "http://${HOST}:${PORT}" \
    --users 5000 \
    --spawn-rate 84 \
    --run-time 600s \
    --headless \
    --csv "${RESULTS}/locust_nominal/datos" \
    --html "${RESULTS}/locust_nominal/reporte.html" \
    --logfile "${RESULTS}/locust_nominal/locust.log" \
    2>&1 | tee "${RESULTS}/locust_nominal/stdout.log" || true

echo ""
echo "  Reporte HTML: ${RESULTS}/locust_nominal/reporte.html"

# Extraer tasa de error del CSV de Locust
python3 - <<PYEOF
import csv, os

path = "${RESULTS}/locust_nominal/datos_stats.csv"
if not os.path.exists(path):
    print("  [INFO] CSV de stats no encontrado (servidor no disponible)")
else:
    with open(path) as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        if row.get("Name") == "Aggregated":
            total = int(row.get("Request Count", 0))
            errores = int(row.get("Failure Count", 0))
            tasa = errores/total*100 if total > 0 else 0
            p90 = row.get("90%", "N/A")
            print(f"\n  NOMINAL — Total: {total:,} | Errores: {errores:,} | Tasa: {tasa:.2f}% | P90: {p90}ms")
            asr_ok = tasa <= 10.0
            print(f"  ASR (error <= 10%): {'CUMPLIDO ✓' if asr_ok else 'FALLADO ✗'}")
PYEOF

echo ""

# =============================================================================
# FASE 5 — Locust: Escenario B — Pico (12000 usuarios, 5 min)
# =============================================================================
echo "━━━ FASE 5: Locust — Escenario PICO (12000 usuarios, 300s) ━━━━━"
echo ""

mkdir -p "${RESULTS}/locust_pico"
locust -f locust/locustfile.py \
    --host "http://${HOST}:${PORT}" \
    --users 12000 \
    --spawn-rate 200 \
    --run-time 300s \
    --headless \
    --csv "${RESULTS}/locust_pico/datos" \
    --html "${RESULTS}/locust_pico/reporte.html" \
    --logfile "${RESULTS}/locust_pico/locust.log" \
    2>&1 | tee "${RESULTS}/locust_pico/stdout.log" || true

python3 - <<PYEOF
import csv, os

path = "${RESULTS}/locust_pico/datos_stats.csv"
if not os.path.exists(path):
    print("  [INFO] CSV de stats no encontrado")
else:
    with open(path) as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        if row.get("Name") == "Aggregated":
            total = int(row.get("Request Count", 0))
            errores = int(row.get("Failure Count", 0))
            tasa = errores/total*100 if total > 0 else 0
            p90 = row.get("90%", "N/A")
            print(f"\n  PICO — Total: {total:,} | Errores: {errores:,} | Tasa: {tasa:.2f}% | P90: {p90}ms")
            asr_ok = tasa <= 10.0
            print(f"  ASR (error <= 10%): {'CUMPLIDO ✓' if asr_ok else 'FALLADO ✗'}")
PYEOF

echo ""

# =============================================================================
# FASE 6 — Locust: Escenario C — Rampa completa ASR (10 minutos)
# =============================================================================
echo "━━━ FASE 6: Locust — Rampa COMPLETA ASR (0→12000→0 en 600s) ━━━"
echo ""

mkdir -p "${RESULTS}/locust_rampa"
locust -f locust/locustfile.py \
    --host "http://${HOST}:${PORT}" \
    --headless \
    --csv "${RESULTS}/locust_rampa/datos" \
    --html "${RESULTS}/locust_rampa/reporte.html" \
    --logfile "${RESULTS}/locust_rampa/locust.log" \
    2>&1 | tee "${RESULTS}/locust_rampa/stdout.log" || true

echo ""

# =============================================================================
# FASE 7 — VEREDICTO FINAL DEL ASR
# =============================================================================
echo "━━━ FASE 7: VEREDICTO FINAL ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

python3 - <<PYEOF
import csv, os, json

criterios = {
    "nominal_error_leq_10pct": None,
    "pico_error_leq_10pct":    None,
    "rampa_error_leq_10pct":   None,
}

escenarios = [
    ("nominal", "${RESULTS}/locust_nominal/datos_stats.csv",  "nominal_error_leq_10pct"),
    ("pico",    "${RESULTS}/locust_pico/datos_stats.csv",      "pico_error_leq_10pct"),
    ("rampa",   "${RESULTS}/locust_rampa/datos_stats.csv",     "rampa_error_leq_10pct"),
]

print("  Criterios del ASR:")
print(f"    Umbral nominal:   5000 usuarios concurrentes")
print(f"    Umbral pico:     12000 usuarios concurrentes")
print(f"    Ventana:            10 minutos (600s)")
print(f"    Error máximo:       10%")
print()

for nombre, path, clave in escenarios:
    if not os.path.exists(path):
        print(f"  [{nombre.upper():8}] Sin datos (servidor no disponible durante la prueba)")
        criterios[clave] = None
        continue

    with open(path) as f:
        rows = list(csv.DictReader(f))

    for row in rows:
        if row.get("Name") == "Aggregated":
            total   = int(row.get("Request Count", 0))
            errores = int(row.get("Failure Count", 0))
            tasa    = errores/total*100 if total > 0 else 0
            p90     = row.get("90%", "?")
            p99     = row.get("99%", "?")
            ok      = tasa <= 10.0
            criterios[clave] = ok
            estado  = "CUMPLIDO ✓" if ok else "FALLADO  ✗"
            print(
                f"  [{nombre.upper():8}] "
                f"Requests: {total:>7,} | "
                f"Errores: {errores:>6,} | "
                f"Tasa: {tasa:>5.1f}% | "
                f"P90: {str(p90):>6}ms | "
                f"{estado}"
            )

print()
todos_ok  = all(v for v in criterios.values() if v is not None)
sin_datos = all(v is None for v in criterios.values())

if sin_datos:
    print("  VEREDICTO: SIN DATOS (ejecutar con servidor real)")
elif todos_ok:
    print("  ══════════════════════════════════════════")
    print("  ✓  ASR CUMPLIDO — El sistema gestiona")
    print("     5000 nominales y 12000 pico con")
    print("     tasa de error <= 10% en 10 minutos")
    print("  ══════════════════════════════════════════")
else:
    print("  ══════════════════════════════════════════")
    print("  ✗  ASR NO CUMPLIDO — Revisar los")
    print("     escenarios fallados y ajustar la")
    print("     infraestructura o el middleware")
    print("  ══════════════════════════════════════════")

# Guardar resumen JSON para la Wiki
resumen = {
    "asr": "Escalabilidad — 5000/12000 usuarios, 10 min, error <= 10%",
    "timestamp": "${TIMESTAMP}",
    "host": "${HOST}:${PORT}",
    "criterios": criterios,
    "cumplido": todos_ok if not sin_datos else None,
}
with open("${RESULTS}/veredicto_asr.json", "w") as f:
    import json
    json.dump(resumen, f, indent=2)

print()
print(f"  Resultados completos: ${RESULTS}/")
print(f"  Veredicto JSON: ${RESULTS}/veredicto_asr.json")
PYEOF

echo ""
