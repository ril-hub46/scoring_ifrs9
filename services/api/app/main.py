"""Lancement local : uv run uvicorn app.main:app --reload   (documentation : http://localhost:8000/docs)"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import meta, portfolio, runs, scoring
from src.config import get_settings


def create_app() -> FastAPI:
    app = FastAPI(
        title="Scoring IFRS 9",
        version="0.1.0",
        description="Scoring PD et calcul de l'Expected Credit Loss (ECL = PD × LGD × EAD).",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    for module in (meta, scoring, portfolio, runs):
        app.include_router(module.router)
    return app


app = create_app()
