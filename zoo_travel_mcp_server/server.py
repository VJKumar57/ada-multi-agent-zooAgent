import json
import os
from typing import Any
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from mcp.server.fastmcp import FastMCP


travel_mcp = FastMCP(
    "Zoo Travel Conditions",
    host="0.0.0.0",
    port=int(os.getenv("PORT", "8080")),
)

ZOO_NAME = os.getenv("ZOO_NAME", "Zoo Tour Guide")
ZOO_LATITUDE = float(os.getenv("ZOO_LATITUDE", "41.8781"))
ZOO_LONGITUDE = float(os.getenv("ZOO_LONGITUDE", "-87.6298"))
UPSTREAM_TIMEOUT_SECONDS = float(os.getenv("UPSTREAM_TIMEOUT_SECONDS", "10"))
ROUTE_PROVIDER = os.getenv("ROUTE_PROVIDER", "unavailable").lower()

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


def fetch_json(url: str) -> dict[str, Any]:
    """Fetch a JSON object from an upstream provider."""
    try:
        with urlopen(url, timeout=UPSTREAM_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, json.JSONDecodeError) as error:
        raise RuntimeError("Travel conditions provider is unavailable.") from error


def weather_request_url(current: bool) -> str:
    parameters = {
        "latitude": ZOO_LATITUDE,
        "longitude": ZOO_LONGITUDE,
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


def weather_error_response(error: RuntimeError) -> dict[str, str]:
    return {"status": "error", "error_message": str(error)}


@travel_mcp.tool()
def get_zoo_weather() -> dict[str, Any]:
    """Get current weather conditions at the configured Zoo location."""
    try:
        weather = fetch_json(weather_request_url(current=True))["current"]
    except (KeyError, RuntimeError) as error:
        return weather_error_response(
            error
            if isinstance(error, RuntimeError)
            else RuntimeError("Weather data is unavailable.")
        )

    return {
        "status": "success",
        "zoo_name": ZOO_NAME,
        "source": "Open-Meteo",
        "observed_at": weather.get("time"),
        "temperature_c": weather.get("temperature_2m"),
        "apparent_temperature_c": weather.get("apparent_temperature"),
        "precipitation_mm": weather.get("precipitation"),
        "weather_code": weather.get("weather_code"),
        "wind_speed_kmh": weather.get("wind_speed_10m"),
    }


@travel_mcp.tool()
def get_weather_forecast(days: int = 3) -> dict[str, Any]:
    """Get a one- to seven-day forecast for the configured Zoo location."""
    if not 1 <= days <= 7:
        return {
            "status": "error",
            "error_message": "Forecast days must be between 1 and 7.",
        }
    try:
        daily = fetch_json(weather_request_url(current=False))["daily"]
        forecast = [
            {
                "date": daily["time"][index],
                "weather_code": daily["weather_code"][index],
                "temperature_min_c": daily["temperature_2m_min"][index],
                "temperature_max_c": daily["temperature_2m_max"][index],
                "precipitation_probability_max": daily[
                    "precipitation_probability_max"
                ][index],
            }
            for index in range(days)
        ]
    except (IndexError, KeyError, RuntimeError) as error:
        return weather_error_response(
            error
            if isinstance(error, RuntimeError)
            else RuntimeError("Forecast data is unavailable.")
        )

    return {
        "status": "success",
        "zoo_name": ZOO_NAME,
        "source": "Open-Meteo",
        "forecast": forecast,
    }


def unavailable_route_response(tool_name: str) -> dict[str, str]:
    return {
        "status": "unavailable",
        "error_message": (
            f"{tool_name} is unavailable because ROUTE_PROVIDER={ROUTE_PROVIDER!r} "
            "does not provide live route or traffic data."
        ),
    }


@travel_mcp.tool()
def get_route_to_zoo(origin: str) -> dict[str, str]:
    """Get route details from an origin when a provider is configured."""
    if not origin.strip():
        return {
            "status": "error",
            "error_message": "An origin is required for route planning.",
        }
    return unavailable_route_response("Route planning")


@travel_mcp.tool()
def get_traffic_conditions(origin: str) -> dict[str, str]:
    """Get live traffic conditions from an origin when a provider is configured."""
    if not origin.strip():
        return {
            "status": "error",
            "error_message": "An origin is required for traffic conditions.",
        }
    return unavailable_route_response("Traffic conditions")


if __name__ == "__main__":
    travel_mcp.run(transport="streamable-http")