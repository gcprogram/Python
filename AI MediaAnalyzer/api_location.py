import requests
from math import radians, sin, cos, sqrt, atan2
import logging
from geopy import Nominatim
from typing import Dict, Any, List, Optional, Tuple
from collections import defaultdict

from urllib3.exceptions import NameResolutionError

log = logging.getLogger(__name__)

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
# Reihenfolge der Namensauflösung
NAME_KEYS = ["name:de", "name:en", "name:fr", "name:es", "name", "name:ar"]
overpass_wait = 2 # wait 2 seconds. Can be adapted times 2 when 429 error.
# Priorität der Hauptkategorien (hoch → niedrig)
CATEGORY_PRIORITY = [
    "historic",
    "tourism",
    "natural",
    "leisure",
    "amenity",
]
CATEGORY_WEIGHT = {
    "historic": 100,
    "tourism": 90,
    "amenity": 80,
    "leisure": 60,
    "natural": 50,
}
SUBTYPE_WEIGHT = {
    # religiös / monumental
    "place_of_worship": 85,
    "cathedral": 90,
    "church": 80,
    "mosque": 80,

    # historic
    "monument": 85,
    "memorial": 85,
    "castle": 90,
    "ruins": 80,

    # tourism
    "attraction": 75,
    "viewpoint": 85,
    "museum": 80,

    # neutral
    "library": 40,
    "school": 30,

    # stark abwerten
    "restaurant": -40,
    "cafe": -45,
    "bar": -50,
    "fast_food": -50,
    "toilets": -60,
    "fuel": -60,
    "parking": -70,
}


def haversine_distance_m(lat1, lon1, lat2, lon2) -> float:
    """Berechnet die Distanz zwischen zwei Punkten in Metern."""
    R = 6371000
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * R * atan2(sqrt(a), sqrt(1 - a))


def extract_coords(el: Dict[str, Any]) -> Optional[tuple]:
    """Extrahiert Koordinaten aus node / way / relation."""
    if el.get("type") == "node":
        return el.get("lat"), el.get("lon")

    center = el.get("center")
    if center:
        return center.get("lat"), center.get("lon")

    return None

#
# Namensauflösung name:de, name:en, ...
#
def resolve_name(tags: Dict[str, str]) -> Optional[str]:
    for key in NAME_KEYS:
        if key in tags:
            return tags[key]
    return None

#
# Node Type und Subtype
#
def determine_category(tags: Dict[str, str]) -> Optional[Tuple[str, str]]:
    """
    Liefert (node_type, subtype), z. B. ("amenity", "school")
    """
    for cat in CATEGORY_PRIORITY:
        if cat in tags:
            return cat, tags.get(cat)
    return None

def distance_penalty(distance_m: float) -> float:
    """
    Sanfte Distanzstrafe:
    - bis 50 m fast irrelevant
    - >300 m spürbar
    """
    if distance_m <= 50:
        return 0
    return min(distance_m / 10, 60)

def score_poi(
    category: str,
    subtype: str,
    distance_m: float
) -> float:
    score = 0

    score += CATEGORY_WEIGHT.get(category, 0)
    score += SUBTYPE_WEIGHT.get(subtype, 0)
    score -= distance_penalty(distance_m)

    return score

#
# Suche nächsten POI
# Benutzt: Overpass API (Achtung: Aufrufhäufigkeit höchstens 1/sec, sonst 429 Fehler (Rate Limit)
# You can safely assume that you don't disturb other users when you do less than 10,000 queries per day
# and download less than 1 GB data per day
#
def get_pois_nearby(
    lat: float,
    lon: float,
    radius: int = 500,
    top_n: int = 15,
    max_per_category: int = 3,
    timeout: int = 25,
) -> List[Dict[str, Any]]:
    """
    Liefert priorisierte Top-N POIs im Umkreis, maximal `max_per_category` pro Kategorie.
    """

    query = f"""
    [out:json][timeout:{timeout}];
    (
      node(around:{radius},{lat},{lon})["historic"];
      way(around:{radius},{lat},{lon})["historic"];
      relation(around:{radius},{lat},{lon})["historic"];

      node(around:{radius},{lat},{lon})["tourism"];
      way(around:{radius},{lat},{lon})["tourism"];
      relation(around:{radius},{lat},{lon})["tourism"];

      node(around:{radius},{lat},{lon})["natural"];
      way(around:{radius},{lat},{lon})["natural"];
      relation(around:{radius},{lat},{lon})["natural"];

      node(around:{radius},{lat},{lon})["leisure"];
      way(around:{radius},{lat},{lon})["leisure"];
      relation(around:{radius},{lat},{lon})["leisure"];

      node(around:{radius},{lat},{lon})["amenity"];
      way(around:{radius},{lat},{lon})["amenity"];
      relation(around:{radius},{lat},{lon})["amenity"];
    );
    out center tags;
    """

    try:
        response = requests.post(
            OVERPASS_URL,
            data=query,
            headers={"User-Agent": "AI MediaAnalyzer/1.0 (aimedia.icetoaster@xoxy.net)"},
            timeout=timeout + 5,
        )
    except requests.RequestException as exc:
        log.error("Point of Interests retrieval failed. Are you offline?: %s", exc)
        return []

    if response.status_code == 429:
        log.error("Overpass rate limit (429): %s", response.text)
        return []
    elif response.status_code in (502, 503, 504):
        log.error("Overpass backend error (%s): %s", response.status_code, response.text)
        return []
    elif response.status_code != 200:
        log.error(
            "Unexpected Overpass status %s: %s",
            response.status_code,
            response.text,
        )
        return []

    data = response.json()
    elements = data.get("elements", [])
    if not elements:
        return []

    collected: List[Dict[str, Any]] = []

    for el in elements:
        coords = extract_coords(el)
        if not coords:
            continue

        tags = el.get("tags", {})
        cat_info = determine_category(tags)
        if not cat_info:
            continue

        category, subtype = cat_info
        name = resolve_name(tags)

        el_lat, el_lon = coords
        dist = haversine_distance_m(lat, lon, el_lat, el_lon)

        score = score_poi(category, subtype, dist)

        collected.append({
            "node_type": category,
            "subtype": subtype,
            "name": name,
            "distance_m": round(dist, 1),
            "score": round(score, 1),
        })

    if not collected:
        return []

    collected.sort(key=lambda x: x["score"], reverse=True)
    result = []
    per_category = defaultdict(int)

    for item in collected:
        if per_category[item["node_type"]] >= max_per_category:
            continue

        result.append(item)
        per_category[item["node_type"]] += 1

        if len(result) >= top_n:
            break

    log.info(
        f"[{result[0]['node_type']}:{result[0]['subtype']}] "
        f"{result[0]['name']} – {result[0]['distance_m']} m "
        f"(score={result[0]['score']})"
    )

    return result

def get_pois_nearby2(
    lat: float,
    lon: float,
    radius: int = 500,
    top_n: int = 15,
    max_per_category: int = 3,
    timeout: int = 25,
) -> List[Dict[str, Any]]:
    """
    Liefert priorisierte Top-N POIs im Umkreis, maximal `max_per_category` pro Kategorie.
    """

    query = f"""
    [out:json][timeout:{timeout}];
    (
      node(around:{radius},{lat},{lon})["historic"];
      way(around:{radius},{lat},{lon})["historic"];
      relation(around:{radius},{lat},{lon})["historic"];

      node(around:{radius},{lat},{lon})["tourism"];
      way(around:{radius},{lat},{lon})["tourism"];
      relation(around:{radius},{lat},{lon})["tourism"];

      node(around:{radius},{lat},{lon})["natural"];
      way(around:{radius},{lat},{lon})["natural"];
      relation(around:{radius},{lat},{lon})["natural"];

      node(around:{radius},{lat},{lon})["leisure"];
      way(around:{radius},{lat},{lon})["leisure"];
      relation(around:{radius},{lat},{lon})["leisure"];

      node(around:{radius},{lat},{lon})["amenity"];
      way(around:{radius},{lat},{lon})["amenity"];
      relation(around:{radius},{lat},{lon})["amenity"];
    );
    out center tags;
    """

    try:
        response = requests.post(
            OVERPASS_URL,
            data=query,
            headers={"User-Agent": "AI MediaAnalyzer/1.0 (aimedia.icetoaster@xoxy.net)"},
            timeout=timeout + 5,
        )
    except requests.RequestException as exc:
        log.error("Point of Interests retrieval failed. Are you offline?: %s", exc)
        return []

    if response.status_code == 429:
        log.error("Overpass rate limit (429): %s", response.text)
        return []
    elif response.status_code in (502, 503, 504):
        log.error("Overpass backend error (%s): %s", response.status_code, response.text)
        return []
    elif response.status_code != 200:
        log.error(
            "Unexpected Overpass status %s: %s",
            response.status_code,
            response.text,
        )
        return []

    data = response.json()
    elements = data.get("elements", [])
    if not elements:
        return []

    collected: List[Dict[str, Any]] = []

    for el in elements:
        coords = get_element_coords(el)
        if not coords:
            continue

        tags = el.get("tags", {})
        cat_info = determine_category(tags)
        if not cat_info:
            continue

        node_type, subtype = cat_info
        name = resolve_name(tags)

        el_lat, el_lon = coords
        dist = haversine_distance_m(lat, lon, el_lat, el_lon)

        collected.append(
            {
                "node_type": node_type,
                "subtype": subtype,
                "name": name,
                "distance_m": round(dist, 1),
            }
        )

    if not collected:
        return []

    # Sortierung: Kategorie-Priorität → Distanz
    priority_index = {cat: idx for idx, cat in enumerate(CATEGORY_PRIORITY)}

    collected.sort(
        key=lambda x: (
            priority_index.get(x["node_type"], 999),
            x["distance_m"],
        )
    )

    # Maximal N pro Kategorie
    per_category_count = defaultdict(int)
    result: List[Dict[str, Any]] = []

    for item in collected:
        if per_category_count[item["node_type"]] >= max_per_category:
            continue

        result.append(item)
        per_category_count[item["node_type"]] += 1

        if len(result) >= top_n:
            break

    return result

def test_pois(lat: float, lon: float, radius=500, top_n=15, max_per_category=3) -> dict[str, Any] | None:
    """
    Testfunktion: Ruft get_pois_nearby auf und gibt die gefundenen POIs aus.
    """
    pois = get_pois_nearby(
        lat=lat,
        lon=lon,
        radius=radius,
        top_n=top_n,
        max_per_category=max_per_category,
    )

    if not pois:
        print("Keine POIs gefunden.")
        return

    print(f"Gefundene POIs für ({lat}, {lon}):\n")

    for idx, poi in enumerate(pois, start=1):
        print(
            f"{idx:02d}. "
            f"[{poi['node_type']}:{poi['subtype']}] "
            f"{poi['name'] or '<ohne Namen>'} – "
            f"{poi['distance_m']} m"
        )

    return {
                "node_type": pois[1]['node_type'],
                "subtype": pois[1]['subtype'],
                "name": pois[1]['name'],
                "distance_m": round(pois[1]['distance_m'],0)
    }

###########################################################
# Wandelt latitude, longitude in einen Ortsnamen um.
# Darf nicht häufiger als 1/sec aufgerufen werden, sonst Fehler 429. Rate limit.
#
# Parts Elements:
# {'aeroway': 'B', 'road': 'Circuit 2', 'town': 'Tremblay-en-France', 'municipality': 'Le Raincy', 'county': 'Seine-Saint-Denis', 'ISO3166-2-lvl6': 'FR-93', 'state': 'Île-de-France', 'ISO3166-2-lvl4': 'FR-IDF', 'region': 'Metropolitanes Frankreich', 'postcode': '93290', 'country': 'Frankreich', 'country_code': 'fr'}
# {'road': 'Circuit 2', 'town': 'Tremblay-en-France', 'municipality': 'Le Raincy', 'county': 'Seine-Saint-Denis', 'ISO3166-2-lvl6': 'FR-93', 'state': 'Île-de-France', 'ISO3166-2-lvl4': 'FR-IDF', 'region': 'Metropolitanes Frankreich', 'postcode': '93290', 'country': 'Frankreich', 'country_code': 'fr'}
# {'road': 'Rue de la Grande Borne', 'village': 'Le Mesnil-Amelot', 'municipality': 'Meaux', 'county': 'Seine-et-Marne', 'ISO3166-2-lvl6': 'FR-77', 'region': 'Metropolitanes Frankreich', 'postcode': '77990', 'country': 'Frankreich', 'country_code': 'fr'}
###########################################################
def reverse_geocode(lat:float, lon:float) -> str:
    """Wandelt Koordinaten in einen Ortsnamen um (Nominatim - uses OpenStreetMap)."""
    if not lat or not lon:
        return ""

    try:
        geolocator = Nominatim(user_agent="AI MediaAnalyzer/v0.8")
        location = geolocator.reverse((lat, lon), language="en", timeout=10)
        loc:str = "<None>"
        if location and location.address:
            #log.info(f"{}")
            log.info(f"name={location.raw.get("name")}")
            log.info(f"display_name={location.raw.get("display_name")}")
            loc =  location.raw.get("name") or location.raw.get("display_name")
            parts = location.raw.get("address", {})
            for adr_type in {"country_code", "house_number", "road", "street", "postcode", "city", "town", "village", "hamlet", "municipality", "region", "state", "country"}:
                if parts.get(adr_type):
                    if loc:
                       loc += ", "
                       loc += f"{parts.get(adr_type)}"

            log.info(f"reverse_geocode(): Address={loc}")
        return loc
    except NameResolutionError:
        log.info(f"Reverse Address resolution by lat,lon can only be done online. Cannot resolve URL.")
    except urllib3.exceptions.MaxRetryError:
        log.info(f"Reverse Address resolution by lat,lon can only be done online. Retry max exceeded.")
    except requests.exceptions.ConnectionError:
        log.info(f"Reverse Address resolution by lat,lon can only be done online. Connection Error.")
    except eopy.exc.GeocoderUnavailable:
        log.info(f"Reverse Address resolution by lat,lon can only be done online. Nominatim unavailable.")
    except Exception:
        log.exception("reverse_geocode() Exception Nominatim")
    return "<error>"
