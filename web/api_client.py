"""Client HTTP de l'API. URL configurable via SCORING_API_URL (http://api:8000 dans docker-compose)."""
import os

import httpx
import streamlit as st

API_URL = os.environ.get("SCORING_API_URL", "http://localhost:8000")


class ApiError(Exception):
    pass


@st.cache_resource
def _client() -> httpx.Client:
    return httpx.Client(base_url=API_URL, timeout=30)


def _request(method: str, path: str, **kwargs):
    try:
        response = _client().request(method, path, **kwargs)
    except httpx.HTTPError as exc:
        raise ApiError(f"API injoignable ({API_URL}) : {exc}") from exc
    if response.is_error:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        raise ApiError(f"Erreur {response.status_code} : {detail}")
    return response.json()


@st.cache_data(ttl=300)
def reference() -> dict:
    return _request("GET", "/reference")


def score(payload: dict) -> dict:
    return _request("POST", "/score", json=payload)


@st.cache_data(ttl=60)
def portfolio_summary(dataset: str | None = None) -> dict:
    return _request("GET", "/portfolio/summary", params={"dataset": dataset} if dataset else None)


@st.cache_data(ttl=60)
def loans(**params) -> dict:
    return _request("GET", "/loans", params={k: v for k, v in params.items() if v is not None})


@st.cache_data(ttl=30)
def model_runs() -> list[dict]:
    return _request("GET", "/model-runs")


@st.cache_data(ttl=30)
def etl_runs(limit: int = 50) -> list[dict]:
    return _request("GET", "/etl-runs", params={"limit": limit})
