from time import perf_counter
from typing import Any, Dict, List, Tuple

import requests

from app.config import settings


def _base_url(url: str) -> str:
    return url.rstrip("/")


def fetch_status(url: str, token: str) -> Tuple[Dict[str, Any], int]:
    endpoint = f"{_base_url(url)}/api/v1/status.json"
    start = perf_counter()
    response = requests.get(
        endpoint,
        params={"token": token},
        timeout=settings.requests_timeout_seconds,
    )
    latency_ms = int((perf_counter() - start) * 1000)
    response.raise_for_status()
    return response.json(), latency_ms


def fetch_entries(url: str, token: str, count: int = 8000) -> List[Dict[str, Any]]:
    endpoint = f"{_base_url(url)}/api/v1/entries/sgv.json"
    response = requests.get(
        endpoint,
        params={"count": count, "token": token},
        timeout=settings.requests_timeout_seconds,
    )
    response.raise_for_status()
    return response.json()


def fetch_treatments(url: str, token: str, count: int = 2000) -> List[Dict[str, Any]]:
    """Fetch treatment records from Nightscout."""
    endpoint = f"{_base_url(url)}/api/v1/treatments.json"
    response = requests.get(
        endpoint,
        params={"count": count, "token": token},
        timeout=settings.requests_timeout_seconds,
    )
    response.raise_for_status()
    return response.json()
