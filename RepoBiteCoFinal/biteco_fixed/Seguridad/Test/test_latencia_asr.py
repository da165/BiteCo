"""
Test de Latencia - Validación del ASR de 100ms
================================================
Compara Prueba A (Secuencial) vs Prueba B (Con Broker/Microservicios)

Este script es el equivalente programático del experimento JMeter.
Úsalo para:
  1. Verificar en desarrollo antes de correr JMeter en EC2
  2. Generar reporte automático de latencias
  3. Validar el ASR: latencia < 100ms

Requisitos:
    pip install requests statistics tabulate

Uso:
    # Prueba contra servidor local:
    python test_latencia_asr.py --host http://localhost:8002 --usuarios 1 10 50 100 500

    # Prueba contra EC2:
    python test_latencia_asr.py --host http://<IP_EC2>:8002 --usuarios 1 50 100 500
"""

import argparse
import statistics
import time
import threading
import requests
from dataclasses import dataclass, field
from typing import List
from tabulate import tabulate


# ─────────────────────────────────────────────
# Configuración
# ─────────────────────────────────────────────
LIMITE_ASR_MS = 100          # Requerimiento: < 100ms
LIMITE_DEGRADACION_MS = 1000  # Punto de quiebre secundario: 1000ms
PROJECT_ID = "proyecto-experimento"
MES = "2024-11"


@dataclass
class ResultadoPeticion:
    latencia_ms: float
    status_code: int
    exitosa: bool
    origen: str = ""  # 'cache', 'base_de_datos', 'microservicio_aws'


@dataclass
class ResultadoRonda:
    usuarios_concurrentes: int
    latencias: List[float] = field(default_factory=list)
    errores: int = 0
    modo: str = "secuencial"

    @property
    def promedio_ms(self):
        return statistics.mean(self.latencias) if self.latencias else 0

    @property
    def p95_ms(self):
        if len(self.latencias) < 2:
            return self.latencias[0] if self.latencias else 0
        return statistics.quantiles(self.latencias, n=20)[18]  # percentil 95

    @property
    def p99_ms(self):
        if len(self.latencias) < 2:
            return self.latencias[0] if self.latencias else 0
        return statistics.quantiles(self.latencias, n=100)[98]  # percentil 99

    @property
    def max_ms(self):
        return max(self.latencias) if self.latencias else 0

    @property
    def min_ms(self):
        return min(self.latencias) if self.latencias else 0

    @property
    def cumple_asr(self):
        return self.promedio_ms < LIMITE_ASR_MS

    @property
    def tasa_error(self):
        total = len(self.latencias) + self.errores
        return (self.errores / total * 100) if total > 0 else 0


def hacer_peticion(url: str, resultados: list, lock: threading.Lock):
    """Hace una petición HTTP y registra la latencia en ms."""
    inicio = time.perf_counter()
    try:
        resp = requests.get(url, timeout=5)
        latencia_ms = (time.perf_counter() - inicio) * 1000
        exitosa = resp.status_code == 200
        origen = resp.json().get("origen", "") if exitosa else ""
        resultado = ResultadoPeticion(
            latencia_ms=latencia_ms,
            status_code=resp.status_code,
            exitosa=exitosa,
            origen=origen
        )
    except Exception as e:
        latencia_ms = (time.perf_counter() - inicio) * 1000
        resultado = ResultadoPeticion(
            latencia_ms=latencia_ms,
            status_code=0,
            exitosa=False
        )

    with lock:
        resultados.append(resultado)


def ejecutar_ronda_concurrente(url: str, n_usuarios: int, modo: str) -> ResultadoRonda:
    """
    Lanza n_usuarios hilos simultáneos al endpoint y recoge latencias.
    Simula la carga concurrente del escenario JMeter.
    """
    resultado_ronda = ResultadoRonda(usuarios_concurrentes=n_usuarios, modo=modo)
    resultados_raw = []
    lock = threading.Lock()

    hilos = [
        threading.Thread(target=hacer_peticion, args=(url, resultados_raw, lock))
        for _ in range(n_usuarios)
    ]

    # Lanzar todos los hilos al mismo tiempo
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    for r in resultados_raw:
        if r.exitosa:
            resultado_ronda.latencias.append(r.latencia_ms)
        else:
            resultado_ronda.errores += 1

    return resultado_ronda


def imprimir_tabla_resultados(resultados: List[ResultadoRonda]):
    """Imprime tabla comparativa de resultados."""
    print("\n" + "=" * 90)
    print(f"📊 RESULTADOS DEL EXPERIMENTO — ASR: latencia promedio < {LIMITE_ASR_MS}ms")
    print("=" * 90)

    headers = [
        "Modo", "Usuarios", "Promedio (ms)", "P95 (ms)", "P99 (ms)",
        "Max (ms)", "Errores %", f"✅ ASR <{LIMITE_ASR_MS}ms"
    ]
    filas = []

    for r in resultados:
        cumple = "✅ SÍ" if r.cumple_asr else "❌ NO"
        filas.append([
            r.modo,
            r.usuarios_concurrentes,
            f"{r.promedio_ms:.2f}",
            f"{r.p95_ms:.2f}",
            f"{r.p99_ms:.2f}",
            f"{r.max_ms:.2f}",
            f"{r.tasa_error:.1f}%",
            cumple
        ])

    print(tabulate(filas, headers=headers, tablefmt="grid"))

    # Punto de quiebre
    print("\n📍 ANÁLISIS DE PUNTOS DE QUIEBRE:")
    modos = set(r.modo for r in resultados)
    for modo in modos:
        rondas_modo = [r for r in resultados if r.modo == modo]
        quiebre_100 = next((r for r in rondas_modo if not r.cumple_asr), None)
        quiebre_1000 = next((r for r in rondas_modo if r.promedio_ms > LIMITE_DEGRADACION_MS), None)
        print(f"  [{modo}]")
        if quiebre_100:
            print(f"    → Supera {LIMITE_ASR_MS}ms ASR a partir de {quiebre_100.usuarios_concurrentes} usuarios concurrentes")
        else:
            print(f"    → ✅ Cumple ASR en todos los niveles de carga probados")
        if quiebre_1000:
            print(f"    → ⚠️  Supera {LIMITE_DEGRADACION_MS}ms a partir de {quiebre_1000.usuarios_concurrentes} usuarios")


def main():
    parser = argparse.ArgumentParser(description="Test de Latencia ASR < 100ms")
    parser.add_argument(
        "--host-secuencial",
        default="http://localhost:8002",
        help="URL base del orquestador en modo SECUENCIAL"
    )
    parser.add_argument(
        "--host-broker",
        default="http://localhost:8003",
        help="URL base del orquestador en modo CON BROKER"
    )
    parser.add_argument(
        "--usuarios",
        type=int,
        nargs="+",
        default=[1, 10, 50, 100, 200, 500],
        help="Niveles de usuarios concurrentes a probar"
    )
    args = parser.parse_args()

    url_secuencial = f"{args.host_secuencial}/api/reportes/{PROJECT_ID}/{MES}/"
    url_broker = f"{args.host_broker}/api/reportes/{PROJECT_ID}/{MES}/"

    todos_resultados = []

    print(f"\n🔬 Iniciando experimento de latencia")
    print(f"   ASR objetivo: < {LIMITE_ASR_MS}ms")
    print(f"   Project ID: {PROJECT_ID} | Mes: {MES}")
    print(f"   Niveles de carga: {args.usuarios}")

    for n_usuarios in args.usuarios:
        print(f"\n⏳ Probando con {n_usuarios} usuarios concurrentes...")

        # Prueba A: Secuencial
        print(f"   [A] Modo Secuencial → {url_secuencial}")
        ronda_sec = ejecutar_ronda_concurrente(url_secuencial, n_usuarios, "Secuencial")
        todos_resultados.append(ronda_sec)
        print(f"       Promedio: {ronda_sec.promedio_ms:.2f}ms | Errores: {ronda_sec.errores}")

        # Prueba B: Con Broker
        print(f"   [B] Modo Broker → {url_broker}")
        ronda_broker = ejecutar_ronda_concurrente(url_broker, n_usuarios, "Con Broker")
        todos_resultados.append(ronda_broker)
        print(f"       Promedio: {ronda_broker.promedio_ms:.2f}ms | Errores: {ronda_broker.errores}")

    imprimir_tabla_resultados(todos_resultados)

    # Guardar CSV para análisis posterior
    csv_path = "resultados_latencia.csv"
    with open(csv_path, "w") as f:
        f.write("modo,usuarios,promedio_ms,p95_ms,p99_ms,max_ms,errores_pct,cumple_asr\n")
        for r in todos_resultados:
            f.write(
                f"{r.modo},{r.usuarios_concurrentes},{r.promedio_ms:.2f},"
                f"{r.p95_ms:.2f},{r.p99_ms:.2f},{r.max_ms:.2f},"
                f"{r.tasa_error:.1f},{r.cumple_asr}\n"
            )
    print(f"\n💾 Resultados guardados en: {csv_path}")


if __name__ == "__main__":
    main()
