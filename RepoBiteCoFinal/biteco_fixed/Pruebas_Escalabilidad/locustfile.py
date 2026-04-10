"""
locust/locustfile.py
====================
Prueba de carga para el ASR de Escalabilidad — Bite.Co
ASR: 5000 usuarios nominales, pico 12000, ventana 10 min, error <= 10%

Escenarios:
  - Escenario A: Carga nominal → 5000 usuarios, validar error < 10%
  - Escenario B: Carga pico    → 12000 usuarios, validar error < 10%
  - Escenario C: Rampa completa → 0→5000→12000→5000→0 en 10 minutos

Cómo ejecutar:

  # Instalar Locust:
  pip install locust

  # Modo interactivo (con UI web en http://localhost:8089):
  locust -f locustfile.py --host http://IP_SERVIDOR

  # Modo headless — Escenario A (5000 usuarios nominales, 10 min):
  locust -f locustfile.py --host http://IP_SERVIDOR \
         --users 5000 --spawn-rate 100 \
         --run-time 600s --headless \
         --csv results/escenario_A \
         --html results/escenario_A.html

  # Modo headless — Escenario B (12000 usuarios pico):
  locust -f locustfile.py --host http://IP_SERVIDOR \
         --users 12000 --spawn-rate 200 \
         --run-time 600s --headless \
         --csv results/escenario_B \
         --html results/escenario_B.html

  # Escenario completo con LoadShape (automático):
  locust -f locustfile.py --host http://IP_SERVIDOR \
         --headless --csv results/rampa_completa \
         --html results/rampa_completa.html
"""

import json
import time
import random
from locust import HttpUser, task, between, events
from locust.runners import MasterRunner, WorkerRunner
from locust import LoadTestShape


# ---------------------------------------------------------------------------
# Datos de prueba
# ---------------------------------------------------------------------------
PROYECTOS = [f"proyecto-{i:04d}" for i in range(1, 501)]
MESES = [
    f"{y}-{m:02d}"
    for y in [2024, 2025]
    for m in range(1, 13)
]
USUARIOS_TEST = [
    {"email": f"usuario{i}@biteco.com", "password": f"Pass{i}Segura!"}
    for i in range(1, 1001)
]


# ---------------------------------------------------------------------------
# Colectores de métricas custom para el reporte del ASR
# ---------------------------------------------------------------------------
_metricas = {
    "total_requests": 0,
    "total_errors": 0,
    "total_503": 0,
    "total_429": 0,
    "tiempos_respuesta": [],
    "inicio": None,
}


@events.request.add_listener
def on_request(request_type, name, response_time, response_length,
               response, context, exception, **kwargs):
    _metricas["total_requests"] += 1
    if exception or (response and response.status_code >= 500):
        _metricas["total_errors"] += 1
    if response:
        if response.status_code == 503:
            _metricas["total_503"] += 1
        elif response.status_code == 429:
            _metricas["total_429"] += 1
    _metricas["tiempos_respuesta"].append(response_time)


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    _metricas["inicio"] = time.time()
    print("\n" + "="*60)
    print("  INICIO — Prueba de escalabilidad ASR Bite.Co")
    print(f"  Objetivo: 5000 nominal / 12000 pico / error <= 10%")
    print("="*60)


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    total = _metricas["total_requests"]
    errores = _metricas["total_errors"]
    duracion = time.time() - (_metricas["inicio"] or time.time())

    tasa_error = (errores / total * 100) if total > 0 else 0
    tiempos = sorted(_metricas["tiempos_respuesta"])
    p50 = tiempos[int(len(tiempos) * 0.50)] if tiempos else 0
    p90 = tiempos[int(len(tiempos) * 0.90)] if tiempos else 0
    p99 = tiempos[int(len(tiempos) * 0.99)] if tiempos else 0

    print("\n" + "="*60)
    print("  RESUMEN FINAL — ASR Escalabilidad")
    print("="*60)
    print(f"  Duración:         {duracion:.1f}s ({duracion/60:.1f} min)")
    print(f"  Total requests:   {total:,}")
    print(f"  Errores (5xx):    {errores:,}")
    print(f"  503 (sobrecarga): {_metricas['total_503']:,}")
    print(f"  429 (rate limit): {_metricas['total_429']:,}")
    print(f"  Tasa de error:    {tasa_error:.2f}%")
    print(f"  P50 latencia:     {p50:.0f}ms")
    print(f"  P90 latencia:     {p90:.0f}ms")
    print(f"  P99 latencia:     {p99:.0f}ms")
    print()

    # Evaluar ASR
    cumple = tasa_error <= 10.0
    print(f"  ASR CUMPLIDO: {'SI ✓' if cumple else 'NO ✗'}")
    print(f"  (Tasa de error {tasa_error:.2f}% {'<=' if cumple else '>'} 10%)")
    print("="*60 + "\n")


# ---------------------------------------------------------------------------
# Usuarios de Locust — Comportamientos
# ---------------------------------------------------------------------------
class UsuarioFinanciero(HttpUser):
    """
    Simula un usuario financiero que consulta reportes de gastos.
    Es el flujo principal del sistema Bite.Co.
    """
    wait_time = between(0.5, 2.0)  # Pausa entre requests: 0.5 a 2 segundos

    def on_start(self):
        """Login al iniciar el usuario."""
        creds = random.choice(USUARIOS_TEST)
        with self.client.post(
            "/auth/login/",
            json={"email": creds["email"], "password": creds["password"]},
            catch_response=True,
            name="POST /auth/login/",
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            elif resp.status_code in (503, 429):
                # El sistema está bajo carga — no es un error de test
                resp.success()
            else:
                resp.failure(f"Login falló con {resp.status_code}")

    @task(5)
    def consultar_reporte(self):
        """
        Tarea principal (peso 5): consultar reporte de gastos.
        Este es el endpoint crítico del ASR.
        """
        project_id = random.choice(PROYECTOS)
        mes = random.choice(MESES)

        with self.client.get(
            f"/api/reportes/{project_id}/{mes}/",
            catch_response=True,
            name="GET /api/reportes/{project}/{mes}/",
        ) as resp:
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    if "origen" not in data:
                        resp.failure("Respuesta 200 sin campo 'origen'")
                    else:
                        resp.success()
                except json.JSONDecodeError:
                    resp.failure("Respuesta 200 no es JSON válido")

            elif resp.status_code == 503:
                # El sistema está en pico — es el comportamiento esperado
                # NO contar como error de Locust, pero sí para métricas ASR
                resp.success()

            elif resp.status_code == 429:
                # Rate limit — comportamiento esperado en carga alta
                resp.success()

            else:
                resp.failure(f"Error inesperado: {resp.status_code}")

    @task(2)
    def consultar_costos_aws(self):
        """Tarea secundaria (peso 2): consultar costos AWS directamente."""
        project_id = random.choice(PROYECTOS[:50])

        with self.client.get(
            f"/api/aws/costos/{project_id}/",
            catch_response=True,
            name="GET /api/aws/costos/{project}/",
        ) as resp:
            if resp.status_code in (200, 503, 429):
                resp.success()
            else:
                resp.failure(f"Error AWS: {resp.status_code}")

    @task(1)
    def health_check(self):
        """Tarea de monitoreo (peso 1): verificar estado del sistema."""
        with self.client.get(
            "/health/",
            catch_response=True,
            name="GET /health/",
        ) as resp:
            if resp.status_code in (200, 206):
                try:
                    data = resp.json()
                    # Loguear si el sistema entra en modo degradado o sobrecarga
                    if data.get("estado") == "sobrecarga":
                        print(
                            f"[ALERTA] Sistema en SOBRECARGA: "
                            f"{data.get('usuarios_activos')} usuarios activos"
                        )
                    resp.success()
                except json.JSONDecodeError:
                    resp.failure("Health check no retornó JSON")
            else:
                resp.failure(f"Health check falló: {resp.status_code}")


class UsuarioAdminMonitoreo(HttpUser):
    """
    Simula administradores que monitorean el sistema durante la carga.
    Proporción baja (1 admin por cada 50 usuarios financieros).
    """
    wait_time = between(5, 15)
    weight = 1  # 1 de cada ~51 usuarios será de este tipo

    @task
    def verificar_health(self):
        with self.client.get("/health/", catch_response=True,
                             name="GET /health/ [admin]") as resp:
            if resp.status_code in (200, 206):
                resp.success()
            else:
                resp.failure(f"Health check admin: {resp.status_code}")


# ---------------------------------------------------------------------------
# LoadShape — Rampa completa en 10 minutos (el escenario del ASR)
# ---------------------------------------------------------------------------
class RampaEscalabilidadASR(LoadTestShape):
    """
    Perfil de carga que simula el escenario completo del ASR en 10 minutos:

    Tiempo (s) | Usuarios | Descripción
    -----------|----------|---------------------------
    0   - 60   | 0→1000   | Arranque gradual
    60  - 180  | 1000→5000| Carga nominal (ASR umbral normal)
    180 - 300  | 5000     | Carga nominal sostenida (2 min)
    300 - 420  | 5000→12000| Escalada al pico (ASR umbral pico)
    420 - 480  | 12000    | Pico sostenido (1 min) — el momento crítico
    480 - 540  | 12000→5000| Descenso del pico
    540 - 600  | 5000→500 | Vuelta a normalidad

    Total: 600 segundos = 10 minutos exactos (ventana del ASR)
    """

    stages = [
        # (tiempo_acumulado_s, usuarios_objetivo, spawn_rate)
        {"duration": 60,  "users": 1000,  "spawn_rate": 17},
        {"duration": 180, "users": 5000,  "spawn_rate": 34},
        {"duration": 300, "users": 5000,  "spawn_rate": 0},
        {"duration": 420, "users": 12000, "spawn_rate": 58},
        {"duration": 480, "users": 12000, "spawn_rate": 0},
        {"duration": 540, "users": 5000,  "spawn_rate": 117},
        {"duration": 600, "users": 500,   "spawn_rate": 75},
    ]

    def tick(self):
        run_time = self.get_run_time()

        for stage in self.stages:
            if run_time < stage["duration"]:
                tick_data = (stage["users"], stage["spawn_rate"])
                return tick_data

        return None  # Terminar la prueba
