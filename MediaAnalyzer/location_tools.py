import functools
from typing import Optional

import requests


class NearbyLandmarkResolver:
    """
    Resolves nearby landmarks using OpenStreetMap (Nominatim)
    based on GPS coordinates. Designed for performance and
    defensive metadata enrichment.
    """

    OSM_POI_KEYS = {
        "tourism": {"attraction", "museum", "viewpoint"},
        "historic": {"monument", "castle", "ruins"},
        "amenity": {"place_of_worship"},
        "leisure": {"park"}
    }

    def __init__(
        self,
        user_agent: str = "MediaAnalyzer/1.0",
        timeout: int = 8,
        cache_size: int = 10_000
    ):
        self.user_agent = user_agent
        self.timeout = timeout

        # Wrap cached resolver
        self._cached_resolve = functools.lru_cache(
            maxsize=cache_size
        )(self._resolve_uncached)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def resolve(
        self,
        lat: float,
        lon: float,
        precision: int = 5
    ) -> Optional[str]:
        """
        Resolve a nearby landmark name for given GPS coordinates.
        Coordinates are rounded to reduce API calls.
        """
        lat_r = round(lat, precision)
        lon_r = round(lon, precision)

        return self._cached_resolve(lat_r, lon_r)

    def merge_with_caption(
        self,
        caption: str,
        landmark: Optional[str]
    ) -> str:
        """
        Merge BLIP caption with nearby landmark defensively.
        """
        if not landmark:
            return caption

        return (
            f"{caption} "
            f"The image was taken near {landmark}."
        )

    # ------------------------------------------------------------------
    # Internal logic
    # ------------------------------------------------------------------

    def _resolve_uncached(
        self,
        lat: float,
        lon: float
    ) -> Optional[str]:
        data = self._query_nominatim(lat, lon)
        return self._extract_landmark(data)

    def _query_nominatim(
        self,
        lat: float,
        lon: float
    ) -> dict:
        url = "https://nominatim.openstreetmap.org/reverse"
        params = {
            "lat": lat,
            "lon": lon,
            "format": "json",
            "zoom": 18,
            "addressdetails": 1
        }
        headers = {
            "User-Agent": self.user_agent
        }

        r = requests.get(
            url,
            params=params,
            headers=headers,
            timeout=self.timeout
        )
        r.raise_for_status()
        return r.json()

    def _extract_landmark(
        self,
        osm_data: dict
    ) -> Optional[str]:
        address = osm_data.get("address", {})

        for key, allowed_values in self.OSM_POI_KEYS.items():
            val = address.get(key)
            if val in allowed_values:
                return (
                    osm_data.get("name")
                    or osm_data.get("display_name")
                )

        return None
