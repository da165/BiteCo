#!/usr/bin/env python3
"""
scripts/generar_datos_escalabilidad.py
=======================================
Genera el CSV 'datos_escalabilidad.csv' requerido por JMeter y Locust.
Incluye 12000+ filas únicas de (project_id, mes, email, password)
para que los threads de JMeter no colisionen en el mismo recurso.

Uso:
  python generar_datos_escalabilidad.py --usuarios 12000 --output datos_escalabilidad.csv
"""
import csv
import argparse
import random

PROYECTOS = [f"proyecto-{i:04d}" for i in range(1, 1001)]
MESES = [f"{y}-{m:02d}" for y in [2024, 2025] for m in range(1, 13)]


def generar(n_usuarios: int, output: str):
    with open(output, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["project_id", "mes", "email", "password"])
        for i in range(1, n_usuarios + 1):
            writer.writerow([
                random.choice(PROYECTOS),
                random.choice(MESES),
                f"usuario{i}@biteco.com",
                f"Pass{i}Segura!",
            ])
    print(f"Generado: {output} ({n_usuarios} filas)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--usuarios", type=int, default=12000)
    parser.add_argument("--output",   default="datos_escalabilidad.csv")
    args = parser.parse_args()
    generar(args.usuarios, args.output)
