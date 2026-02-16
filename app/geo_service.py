"""Google Maps geocoding & navigation URL construction."""

import logging
from urllib.parse import quote

import aiohttp

from app.config import GOOGLE_MAPS_API_KEY

logger = logging.getLogger(__name__)

_GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"


async def geocode(query: str) -> dict | None:
    """Geocode a place name/address to WGS84 coordinates.

    Returns {"lat": float, "lng": float, "address": str} on success,
    or None if no results or API error.
    """
    if not GOOGLE_MAPS_API_KEY:
        logger.error("Google Maps API key not configured")
        return None

    params = {
        "address": query,
        "key": GOOGLE_MAPS_API_KEY,
        "language": "ko",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                _GEOCODE_URL,
                params=params,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.error("Google geocode API returned status %s: %s", resp.status, body)
                    return None
                data = await resp.json()
    except Exception:
        logger.exception("Google geocode request failed")
        return None

    results = data.get("results", [])
    if not results:
        logger.warning("Google geocode returned no results for query=%s, status=%s", query, data.get("status"))
        return None

    first = results[0]
    location = first["geometry"]["location"]
    return {
        "lat": location["lat"],
        "lng": location["lng"],
        "address": first.get("formatted_address", query),
    }


def build_directions_url(
    start_lat: float,
    start_lng: float,
    dest_lat: float,
    dest_lng: float,
    dest_name: str,
) -> str:
    """Build a Google Maps directions URL."""
    encoded_name = quote(dest_name)
    return (
        f"https://www.google.com/maps/dir/"
        f"{start_lat},{start_lng}/"
        f"{dest_lat},{dest_lng}/"
    )
