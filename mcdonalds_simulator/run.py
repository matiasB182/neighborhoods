"""
Entry point del simulador de escenarios McDonald's.

Uso:
    python run.py                          # usa scenario.yaml por defecto
    python run.py --scenario mi_escenario.yaml
    python run.py --recalcular-elasticidades   # recalcula coeficientes del histórico

GENIA ejecuta:
    python run.py --scenario scenario.yaml
"""

import argparse
import logging
import sys
from pathlib import Path

import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Simulador de escenarios McDonald's")
    parser.add_argument(
        "--scenario", default="scenario.yaml",
        help="Path al archivo YAML con el escenario (default: scenario.yaml)"
    )
    parser.add_argument(
        "--recalcular-elasticidades", action="store_true",
        help="Recalcula y persiste las elasticidades históricas antes de simular"
    )
    parser.add_argument(
        "--solo-recalcular", action="store_true",
        help="Solo recalcula elasticidades y termina (sin correr escenario)"
    )
    args = parser.parse_args()

    # Recálculo de elasticidades (job mensual o manual)
    if args.recalcular_elasticidades or args.solo_recalcular:
        log.info("Recalculando elasticidades históricas...")
        from core.elasticidades import calcular_y_guardar
        calcular_y_guardar()
        if args.solo_recalcular:
            log.info("Listo.")
            return

    # Cargar YAML del escenario
    scenario_path = Path(args.scenario)
    if not scenario_path.exists():
        log.error("No se encontró el archivo de escenario: %s", scenario_path)
        sys.exit(1)

    with open(scenario_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # Ejecutar
    from core.engine import correr_escenario
    df, nombre = correr_escenario(config)

    if df.empty:
        log.error("El escenario no produjo resultados.")
        sys.exit(1)

    # Resumen en consola
    from output.formatter import resumen_consola
    palancas = config.get("palancas", [])
    resumen = resumen_consola(df, nombre, palancas)
    print("\n" + resumen + "\n")

    # Guardar en Redshift + CSV
    from output.writer import guardar
    csv_path = guardar(df, nombre, palancas)
    log.info("CSV disponible en: %s", csv_path)


if __name__ == "__main__":
    main()
