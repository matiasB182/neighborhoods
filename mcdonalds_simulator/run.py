"""
Entry point del simulador de escenarios McDonald's.

Uso:
    python run.py                          # usa scenario.yaml por defecto
    python run.py --scenario mi_escenario.yaml

GENIA ejecuta:
    python run.py --scenario scenario.yaml
"""

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
    import argparse
    parser = argparse.ArgumentParser(description="Simulador de escenarios McDonald's")
    parser.add_argument(
        "--scenario", default="scenario.yaml",
        help="Path al archivo YAML con el escenario (default: scenario.yaml)"
    )
    args = parser.parse_args()

    scenario_path = Path(args.scenario)
    if not scenario_path.exists():
        log.error("No se encontró el archivo de escenario: %s", scenario_path)
        sys.exit(1)

    with open(scenario_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    from core.engine import correr_escenario
    df, nombre = correr_escenario(config)

    if df.empty:
        log.error("El escenario no produjo resultados.")
        sys.exit(1)

    from output.formatter import resumen_consola
    palancas = config.get("palancas", [])
    resumen = resumen_consola(df, nombre, palancas)
    print("\n" + resumen + "\n")

    from output.writer import guardar
    csv_path = guardar(df, nombre, palancas)
    log.info("CSV disponible en: %s", csv_path)


if __name__ == "__main__":
    main()
