import json
import math
import os
import time
from collections import OrderedDict
from datetime import date
from typing import Any
from urllib.error import URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from mcp.server.fastmcp import FastMCP


travel_mcp = FastMCP(
    "Zoo Travel Conditions",
    host="0.0.0.0",
    port=int(os.getenv("PORT", "8080")),
)

UPSTREAM_TIMEOUT_SECONDS = float(os.getenv("UPSTREAM_TIMEOUT_SECONDS", "10"))
NOMINATIM_USER_AGENT = os.getenv(
    "NOMINATIM_USER_AGENT", "zoo-tour-guide-demo/1.0 (contact: example@example.com)"
)
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OSRM_URL = "https://router.project-osrm.org/route/v1/driving"

DEFAULT_ZOO_LOCATIONS = [
    {
        "id": "chicago",
        "name": "Chicago Zoo Demo",
        "address": "Chicago, Illinois (demonstration location)",
        "latitude": 41.9210,
        "longitude": -87.6335,
    },
    {
        "id": "san_diego",
        "name": "San Diego Zoo Demo",
        "address": "San Diego, California (demonstration location)",
        "latitude": 32.7353,
        "longitude": -117.1490,
    },
    {
        "id": "bronx",
        "name": "Bronx Zoo Demo",
        "address": "Bronx, New York (demonstration location)",
        "latitude": 40.8506,
        "longitude": -73.8769,
    },
    {
        "id": "washington_dc",
        "name": "Washington, DC Zoo Demo",
        "address": "Washington, DC (demonstration location)",
        "latitude": 38.9296,
        "longitude": -77.0498,
    },
]


def load_zoo_locations() -> dict[str, dict[str, Any]]:
    """Load validated location data from server-side configuration."""
    configured_locations = os.getenv("ZOO_LOCATIONS_JSON")
    locations = (
        json.loads(configured_locations)
        if configured_locations
        else DEFAULT_ZOO_LOCATIONS
    )
    if not isinstance(locations, list):
        raise ValueError("ZOO_LOCATIONS_JSON must be a JSON array.")

    registry = {}
    for location in locations:
        required_fields = {"id", "name", "address", "latitude", "longitude"}
        has_required_fields = (
            isinstance(location, dict) and required_fields <= location.keys()
        )
        if not has_required_fields:
            raise ValueError(
                "Each zoo location must define id, name, address, latitude, "
                "and longitude."
            )
        zoo_id = str(location["id"]).strip().lower()
        if not zoo_id or zoo_id in registry:
            raise ValueError("Zoo location ids must be unique and non-empty.")
        registry[zoo_id] = {
            "id": zoo_id,
            "name": str(location["name"]),
            "address": str(location["address"]),
            "latitude": float(location["latitude"]),
            "longitude": float(location["longitude"]),
        }
    return registry


ZOO_LOCATIONS = load_zoo_locations()
CACHE_MAX_ENTRIES = int(os.getenv("TRAVEL_CACHE_MAX_ENTRIES", "200"))
GEOCODING_CACHE_TTL_SECONDS = 14 * 24 * 60 * 60
WEATHER_CACHE_TTL_SECONDS = 15 * 60
FORECAST_CACHE_TTL_SECONDS = 6 * 60 * 60
ROUTE_CACHE_TTL_SECONDS = 60 * 60
geocoding_cache: OrderedDict[str, tuple[float, dict[str, float | str]]] = OrderedDict()
weather_cache: OrderedDict[str, tuple[float, dict[str, Any]]] = OrderedDict()
forecast_cache: OrderedDict[str, tuple[float, dict[str, Any]]] = OrderedDict()
route_cache: OrderedDict[str, tuple[float, dict[str, float]]] = OrderedDict()


def cache_get(cache: OrderedDict, key: str) -> Any | None:
    """Return an unexpired value and retain it as the most recently used entry."""
    entry = cache.get(key)
    if entry is None:
        return None
    expires_at, value = entry
    if time.monotonic() >= expires_at:
        del cache[key]
        return None
    cache.move_to_end(key)
    return value


def cache_set(cache: OrderedDict, key: str, value: Any, ttl_seconds: int) -> None:
    """Store a successful provider response with bounded LRU eviction."""
    cache[key] = (time.monotonic() + ttl_seconds, value)
    cache.move_to_end(key)
    while len(cache) > CACHE_MAX_ENTRIES:
        cache.popitem(last=False)


def fetch_json(url: str, headers: dict[str, str] | None = None) -> Any:
    """Fetch JSON from an upstream provider with a bounded timeout."""
    try:
        request = Request(url, headers=headers or {})
        with urlopen(request, timeout=UPSTREAM_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, json.JSONDecodeError) as error:
        raise RuntimeError("Travel conditions provider is unavailable.") from error


def get_zoo(zoo_id: str) -> dict[str, Any] | None:
    return ZOO_LOCATIONS.get(zoo_id.strip().lower())


def zoo_error_response(zoo_id: str) -> dict[str, str]:
    options = ", ".join(ZOO_LOCATIONS)
    return {
        "status": "error",
        "error_message": f"Unknown zoo_id '{zoo_id}'. Choose one of: {options}.",
    }


def weather_request_url(zoo: dict[str, Any], current: bool) -> str:
    parameters = {
        "latitude": zoo["latitude"],
        "longitude": zoo["longitude"],
        "timezone": "auto",
    }
    if current:
        parameters["current"] = (
            "temperature_2m,apparent_temperature,precipitation,weather_code,"
            "wind_speed_10m"
        )
    else:
        parameters["daily"] = (
            "weather_code,temperature_2m_max,temperature_2m_min,"
            "precipitation_probability_max"
        )
    return f"{OPEN_METEO_URL}?{urlencode(parameters)}"


def error_response(message: str) -> dict[str, str]:
    return {"status": "error", "error_message": message}


def server_date() -> date:
    """Return the current date according to the travel service server."""
    return date.today()


def parse_visit_date(visit_date: str) -> date:
    """Validate a forecast date within the provider's seven-day window."""
    try:
        requested_date = date.fromisoformat(visit_date)
    except ValueError as error:
        raise ValueError("visit_date must use ISO format: YYYY-MM-DD.") from error
    days_ahead = (requested_date - server_date()).days
    if not 0 <= days_ahead <= 6:
        raise ValueError("visit_date must be between today and six days from today.")
    return requested_date


@travel_mcp.tool()
def get_server_date() -> dict[str, str]:
    """Get the current server date used to resolve relative visit dates."""
    return {"status": "success", "date": server_date().isoformat()}


@travel_mcp.tool()
def list_zoo_locations() -> dict[str, Any]:
    """List available Zoo demonstration locations and their identifiers."""
    return {
        "status": "success",
        "locations": list(ZOO_LOCATIONS.values()),
        "note": "Locations are demonstration data; replace them before production use.",
    }


@travel_mcp.tool()
def get_zoo_location(zoo_id: str) -> dict[str, Any]:
    """Get a Zoo demonstration location by id, including its configured address."""
    zoo = get_zoo(zoo_id)
    if zoo is None:
        return zoo_error_response(zoo_id)
    return {
        "status": "success",
        "location": zoo,
        "note": "This is a demonstration location, not an official Zoo address.",
    }


@travel_mcp.tool()
def get_zoo_weather(zoo_id: str) -> dict[str, Any]:
    """Get current weather conditions for a selected Zoo location."""
    zoo = get_zoo(zoo_id)
    if zoo is None:
        return zoo_error_response(zoo_id)
    try:
        weather = cache_get(weather_cache, zoo["id"])
        if weather is None:
            weather = fetch_json(weather_request_url(zoo, current=True))["current"]
            cache_set(
                weather_cache,
                zoo["id"],
                weather,
                WEATHER_CACHE_TTL_SECONDS,
            )
    except (KeyError, RuntimeError):
        return error_response("Weather data is unavailable.")
    return {
        "status": "success",
        "zoo": zoo,
        "source": "Open-Meteo",
        "observed_at": weather.get("time"),
        "temperature_c": weather.get("temperature_2m"),
        "apparent_temperature_c": weather.get("apparent_temperature"),
        "precipitation_mm": weather.get("precipitation"),
        "weather_code": weather.get("weather_code"),
        "wind_speed_kmh": weather.get("wind_speed_10m"),
    }


@travel_mcp.tool()
def get_weather_forecast(
    zoo_id: str, visit_date: str | None = None, days: int = 3
) -> dict[str, Any]:
    """Get a selected-date or one- to seven-day forecast for a Zoo location."""
    zoo = get_zoo(zoo_id)
    if zoo is None:
        return zoo_error_response(zoo_id)
    try:
        requested_date = parse_visit_date(visit_date) if visit_date else None
    except ValueError as error:
        return error_response(str(error))
    if visit_date is None and not 1 <= days <= 7:
        return error_response("Forecast days must be between 1 and 7.")
    try:
        daily = cache_get(forecast_cache, zoo["id"])
        if daily is None:
            daily = fetch_json(weather_request_url(zoo, current=False))["daily"]
            cache_set(forecast_cache, zoo["id"], daily, FORECAST_CACHE_TTL_SECONDS)
        forecast_entries = [
            {
                "date": daily["time"][index],
                "weather_code": daily["weather_code"][index],
                "temperature_min_c": daily["temperature_2m_min"][index],
                "temperature_max_c": daily["temperature_2m_max"][index],
                "precipitation_probability_max": daily[
                    "precipitation_probability_max"
                ][index],
            }
            for index in range(len(daily["time"]))
        ]
    except (IndexError, KeyError, RuntimeError):
        return error_response("Forecast data is unavailable.")
    if requested_date:
        forecast_entries = [
            entry
            for entry in forecast_entries
            if entry["date"] == requested_date.isoformat()
        ]
        if not forecast_entries:
            return error_response("Forecast data is unavailable for visit_date.")
    else:
        forecast_entries = forecast_entries[:days]
    return {
        "status": "success",
        "zoo": zoo,
        "source": "Open-Meteo",
        "forecast": forecast_entries,
    }


def geocode_address(address: str) -> dict[str, float | str]:
    """Geocode an origin address through Nominatim, caching successful lookups."""
    normalized_address = address.strip()
    if not normalized_address:
        raise ValueError("An origin is required for route planning.")
    cache_key = normalized_address.casefold()
    cached_result = cache_get(geocoding_cache, cache_key)
    if cached_result is not None:
        return cached_result
    parameters = {"q": normalized_address, "format": "jsonv2", "limit": 1}
    results = fetch_json(
        f"{NOMINATIM_URL}?{urlencode(parameters)}",
        headers={"User-Agent": NOMINATIM_USER_AGENT},
    )
    if not isinstance(results, list) or not results:
        raise ValueError("The origin address could not be located.")
    try:
        coordinates = {
            "latitude": float(results[0]["lat"]),
            "longitude": float(results[0]["lon"]),
            "display_name": str(results[0]["display_name"]),
        }
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("The origin address could not be located.") from error
    cache_set(geocoding_cache, cache_key, coordinates, GEOCODING_CACHE_TTL_SECONDS)
    return coordinates


def calculate_route(
    origin: dict[str, float | str], zoo: dict[str, Any]
) -> dict[str, float]:
    """Calculate a traffic-free driving route through OSRM."""
    coordinates = (
        f"{origin['longitude']},{origin['latitude']};"
        f"{zoo['longitude']},{zoo['latitude']}"
    )
    cached_route = cache_get(route_cache, f"{coordinates}:{zoo['id']}")
    if cached_route is not None:
        return cached_route
    route_url = f"{OSRM_URL}/{quote(coordinates, safe=',;')}?overview=false"
    response = fetch_json(route_url)
    try:
        route = response["routes"][0]
        route = {
            "distance_km": round(float(route["distance"]) / 1000, 1),
            "estimated_duration_minutes": round(float(route["duration"]) / 60),
        }
        cache_set(
            route_cache,
            f"{coordinates}:{zoo['id']}",
            route,
            ROUTE_CACHE_TTL_SECONDS,
        )
        return route
    except (IndexError, KeyError, TypeError, ValueError) as error:
        raise RuntimeError("A driving route could not be calculated.") from error


def coordinate_origin(latitude: float, longitude: float) -> dict[str, float | str]:
    """Validate browser-provided coordinates without reverse geocoding them."""
    if (
        isinstance(latitude, bool)
        or isinstance(longitude, bool)
        or not isinstance(latitude, (int, float))
        or not isinstance(longitude, (int, float))
        or not math.isfinite(latitude)
        or not math.isfinite(longitude)
    ):
        raise ValueError("Latitude and longitude must be finite numbers.")
    if not -90 <= latitude <= 90:
        raise ValueError("Latitude must be between -90 and 90.")
    if not -180 <= longitude <= 180:
        raise ValueError("Longitude must be between -180 and 180.")
    return {
        "latitude": round(latitude, 3),
        "longitude": round(longitude, 3),
        "display_name": "Shared location",
    }


@travel_mcp.tool()
def find_nearest_zoo(origin_latitude: float, origin_longitude: float) -> dict[str, Any]:
    """Find the nearest Zoo by traffic-free driving route from shared coordinates."""
    try:
        origin = coordinate_origin(origin_latitude, origin_longitude)
        routes = [
            (zoo, calculate_route(origin, zoo)) for zoo in ZOO_LOCATIONS.values()
        ]
    except (RuntimeError, ValueError) as error:
        return error_response(str(error))
    zoo, route = min(routes, key=lambda item: item[1]["distance_km"])
    return {
        "status": "success",
        "zoo": zoo,
        "source": "OpenStreetMap OSRM",
        "traffic_included": False,
        **route,
    }


@travel_mcp.tool()
def get_route_to_zoo(origin: str, zoo_id: str) -> dict[str, Any]:
    """Get traffic-free driving distance and estimated duration to a selected Zoo."""
    zoo = get_zoo(zoo_id)
    if zoo is None:
        return zoo_error_response(zoo_id)
    try:
        origin_location = geocode_address(origin)
        route = calculate_route(origin_location, zoo)
    except (RuntimeError, ValueError) as error:
        return error_response(str(error))
    return {
        "status": "success",
        "origin": origin_location,
        "zoo": zoo,
        "source": "OpenStreetMap Nominatim and OSRM",
        "traffic_included": False,
        **route,
    }


if __name__ == "__main__":
    travel_mcp.run(transport="streamable-http")