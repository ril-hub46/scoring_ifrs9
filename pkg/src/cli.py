"""Point d'entrée en ligne de commande.

    uv run scoring-ifrs9 rebuild-source [--force]   anciens parquets -> data/raw/data_final.csv
    uv run scoring-ifrs9 ingest                     fichier source   -> raw.loans
    uv run scoring-ifrs9 staging                    raw.loans        -> staging.loans
    uv run scoring-ifrs9 train                      staging.loans    -> modèle PD actif (mart.model_runs)
    uv run scoring-ifrs9 score                      staging + modèle -> mart.pd_scores, mart.ecl_results
    uv run scoring-ifrs9 run-all                    ingest, staging, train, score
"""
import argparse
import logging

from src.config import get_settings
from src.db.session import get_engine
from src.etl.extract import rebuild_source_from_parquets
from src.etl.pipeline import build_staging, ingest_raw, score_portfolio
from src.modeling.pipeline import train_and_register

logger = logging.getLogger("src")

STEPS = {
    "ingest": ingest_raw,
    "staging": build_staging,
    "train": train_and_register,
    "score": score_portfolio,
}


def main() -> None:
    parser = argparse.ArgumentParser(prog="scoring-ifrs9")
    sub = parser.add_subparsers(dest="command", required=True)
    rebuild_cmd = sub.add_parser("rebuild-source", help="Reconstruit le fichier source depuis les anciens parquets")
    rebuild_cmd.add_argument("--force", action="store_true", help="Écrase le fichier source s'il existe")
    sub.add_parser("ingest", help="Charge le fichier source dans raw.loans")
    sub.add_parser("staging", help="Nettoie et impute raw.loans dans staging.loans")
    sub.add_parser("train", help="Entraîne le modèle PD et l'active")
    sub.add_parser("score", help="Calcule PD et ECL du portefeuille avec le modèle actif")
    sub.add_parser("run-all", help="Enchaîne ingest, staging, train et score")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = get_settings()

    if args.command == "rebuild-source":
        if settings.raw_data_path.exists() and not args.force:
            parser.error(f"{settings.raw_data_path} existe déjà (utiliser --force pour l'écraser)")
        n = rebuild_source_from_parquets(settings.train_path, settings.test_path, settings.raw_data_path)
        logger.info("%d prêts écrits dans %s", n, settings.raw_data_path)
        return

    engine = get_engine(settings.database_url)
    steps = list(STEPS) if args.command == "run-all" else [args.command]
    for step in steps:
        STEPS[step](engine, settings)


if __name__ == "__main__":
    main()
