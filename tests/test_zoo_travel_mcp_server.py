from datetime import date

from zoo_travel_mcp_server import server


def setup_function():
    server.geocoding_cache.clear()
    server.weather_cache.clear()
    server.forecast_cache.clear()
    server.route_cache.clear()


def test_list_zoo_locations_returns_four_demonstration_locations():
    locations = server.list_zoo_locations()

    assert locations["status"] == "success"
    assert [location["id"] for location in locations["locations"]] == [
        "chicago",
        "san_diego",
        "bronx",
        "washington_dc",
    ]


def test_get_zoo_location_returns_a_configured_location():
    location = server.get_zoo_location("bronx")

    assert location["status"] == "success"
    assert location["location"]["latitude"] == 40.8506


def test_get_zoo_weather_returns_conditions_for_selected_zoo(monkeypatch):
    monkeypatch.setattr(
        server,
        "fetch_json",
        lambda *args, **kwargs: {
            "current": {
                "time": "2026-08-31T10:00",
                "temperature_2m": 22.5,
                "apparent_temperature": 21.8,
                "precipitation": 0,
                "weather_code": 1,
                "wind_speed_10m": 11.2,
            }
        },
    )

    conditions = server.get_zoo_weather("san_diego")

    assert conditions["status"] == "success"
    assert conditions["zoo"]["id"] == "san_diego"
    assert conditions["temperature_c"] == 22.5


def test_weather_cache_reuses_a_recent_provider_response(monkeypatch):
    calls = []

    def fetch(*args, **kwargs):
        calls.append(args)
        return {"current": {"time": "2026-08-31T10:00"}}

    monkeypatch.setattr(server, "fetch_json", fetch)

    server.get_zoo_weather("chicago")
    server.get_zoo_weather("chicago")

    assert len(calls) == 1


def test_weather_cache_expires(monkeypatch):
    clock = [100.0]
    calls = []
    monkeypatch.setattr(server.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        server,
        "fetch_json",
        lambda *args, **kwargs: calls.append(1) or {"current": {"time": "now"}},
    )

    server.get_zoo_weather("chicago")
    clock[0] += server.WEATHER_CACHE_TTL_SECONDS
    server.get_zoo_weather("chicago")

    assert len(calls) == 2


def test_get_weather_forecast_limits_results_to_requested_days(monkeypatch):
    monkeypatch.setattr(
        server,
        "fetch_json",
        lambda *args, **kwargs: {
            "daily": {
                "time": ["2026-08-31", "2026-09-01"],
                "weather_code": [1, 3],
                "temperature_2m_min": [16, 14],
                "temperature_2m_max": [25, 22],
                "precipitation_probability_max": [10, 40],
            }
        },
    )

    forecast = server.get_weather_forecast("chicago", days=2)

    assert forecast["status"] == "success"
    assert forecast["zoo"]["id"] == "chicago"
    assert len(forecast["forecast"]) == 2


def test_forecast_cache_filters_each_request_after_reuse(monkeypatch):
    calls = []
    monkeypatch.setattr(
        server,
        "fetch_json",
        lambda *args, **kwargs: calls.append(1)
        or {
            "daily": {
                "time": ["2026-08-31", "2026-09-01"],
                "weather_code": [1, 3],
                "temperature_2m_min": [16, 14],
                "temperature_2m_max": [25, 22],
                "precipitation_probability_max": [10, 40],
            }
        },
    )

    first = server.get_weather_forecast("chicago", days=1)
    second = server.get_weather_forecast("chicago", days=2)

    assert len(calls) == 1
    assert len(first["forecast"]) == 1
    assert len(second["forecast"]) == 2


def test_get_weather_forecast_returns_the_requested_visit_date(monkeypatch):
    monkeypatch.setattr(server, "server_date", lambda: date(2026, 8, 31))
    monkeypatch.setattr(
        server,
        "fetch_json",
        lambda *args, **kwargs: {
            "daily": {
                "time": ["2026-08-31", "2026-09-01", "2026-09-03"],
                "weather_code": [1, 3, 51],
                "temperature_2m_min": [16, 14, 18],
                "temperature_2m_max": [25, 22, 27],
                "precipitation_probability_max": [10, 40, 30],
            }
        },
    )

    forecast = server.get_weather_forecast("chicago", visit_date="2026-09-03")

    assert forecast["status"] == "success"
    assert forecast["forecast"] == [
        {
            "date": "2026-09-03",
            "weather_code": 51,
            "temperature_min_c": 18,
            "temperature_max_c": 27,
            "precipitation_probability_max": 30,
        }
    ]


def test_get_weather_forecast_rejects_dates_outside_seven_day_window(monkeypatch):
    monkeypatch.setattr(server, "server_date", lambda: date(2026, 8, 31))

    result = server.get_weather_forecast("chicago", visit_date="2026-09-07")

    assert result == {
        "status": "error",
        "error_message": "visit_date must be between today and six days from today.",
    }


def test_get_weather_forecast_rejects_malformed_visit_dates():
    result = server.get_weather_forecast("chicago", visit_date="coming Sunday")

    assert result == {
        "status": "error",
        "error_message": "visit_date must use ISO format: YYYY-MM-DD.",
    }


def test_weather_tools_reject_unknown_zoo_ids():
    result = server.get_zoo_weather("seattle")

    assert result["status"] == "error"
    assert "Unknown zoo_id 'seattle'" in result["error_message"]


def test_get_weather_forecast_rejects_invalid_day_count():
    result = server.get_weather_forecast("chicago", days=8)

    assert result == {
        "status": "error",
        "error_message": "Forecast days must be between 1 and 7.",
    }


def test_get_route_to_zoo_returns_osrm_distance_and_duration(monkeypatch):
    def route_responses(url, headers=None):
        if url.startswith(server.NOMINATIM_URL):
            return [
                {
                    "lat": "39.5778",
                    "lon": "-75.5123",
                    "display_name": "Delaware, United States",
                }
            ]
        return {"routes": [{"distance": 123400, "duration": 7260}]}

    monkeypatch.setattr(server, "fetch_json", route_responses)
    server.geocoding_cache.clear()

    route = server.get_route_to_zoo("656 Melick Dr, Delaware", "chicago")

    assert route["status"] == "success"
    assert route["distance_km"] == 123.4
    assert route["estimated_duration_minutes"] == 121
    assert route["traffic_included"] is False


def test_find_nearest_zoo_compares_routes_without_geocoding(monkeypatch):
    distances = iter([300000, 2800000, 600000, 700000])
    calls = []

    def route_responses(url, headers=None):
        calls.append(url)
        return {"routes": [{"distance": next(distances), "duration": 3600}]}

    monkeypatch.setattr(server, "fetch_json", route_responses)

    result = server.find_nearest_zoo(40.0, -83.0)

    assert result["status"] == "success"
    assert result["zoo"]["id"] == "chicago"
    assert result["distance_km"] == 300.0
    assert result["traffic_included"] is False
    assert len(calls) == 4
    assert all(not url.startswith(server.NOMINATIM_URL) for url in calls)


def test_find_nearest_zoo_rejects_invalid_coordinates():
    result = server.find_nearest_zoo(91, -83)

    assert result == {
        "status": "error",
        "error_message": "Latitude must be between -90 and 90.",
    }

    result = server.find_nearest_zoo(float("nan"), -83)

    assert result == {
        "status": "error",
        "error_message": "Latitude and longitude must be finite numbers.",
    }


def test_find_nearest_zoo_reuses_cached_routes(monkeypatch):
    calls = []

    def route_responses(url, headers=None):
        calls.append(url)
        return {"routes": [{"distance": 100000, "duration": 3600}]}

    monkeypatch.setattr(server, "fetch_json", route_responses)

    server.find_nearest_zoo(40.0, -83.0)
    server.find_nearest_zoo(40.0, -83.0)

    assert len(calls) == 4


def test_find_nearest_zoo_returns_an_error_when_routing_is_unavailable(monkeypatch):
    monkeypatch.setattr(
        server,
        "fetch_json",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("Unavailable")),
    )

    assert server.find_nearest_zoo(40.0, -83.0) == {
        "status": "error",
        "error_message": "Unavailable",
    }


def test_route_cache_reuses_geocoding_and_osrm_results(monkeypatch):
    calls = []

    def route_responses(url, headers=None):
        calls.append(url)
        if url.startswith(server.NOMINATIM_URL):
            return [{"lat": "39.5778", "lon": "-75.5123", "display_name": "Delaware"}]
        return {"routes": [{"distance": 123400, "duration": 7260}]}

    monkeypatch.setattr(server, "fetch_json", route_responses)

    server.get_route_to_zoo("656 Melick Dr, Delaware", "chicago")
    server.get_route_to_zoo("656 Melick Dr, Delaware", "chicago")

    assert len(calls) == 2


def test_get_route_to_zoo_reports_unknown_origin(monkeypatch):
    monkeypatch.setattr(server, "fetch_json", lambda *args, **kwargs: [])
    server.geocoding_cache.clear()

    result = server.get_route_to_zoo("Unknown place", "chicago")

    assert result == {
        "status": "error",
        "error_message": "The origin address could not be located.",
    }


def test_get_route_to_zoo_requires_an_origin():
    result = server.get_route_to_zoo(" ", "chicago")

    assert result == {
        "status": "error",
        "error_message": "An origin is required for route planning.",
    }


def test_get_route_to_zoo_reports_osrm_failures(monkeypatch):
    def route_responses(url, headers=None):
        if url.startswith(server.NOMINATIM_URL):
            return [{"lat": "39.5778", "lon": "-75.5123", "display_name": "Delaware"}]
        return {"routes": []}

    monkeypatch.setattr(server, "fetch_json", route_responses)
    server.geocoding_cache.clear()

    result = server.get_route_to_zoo("656 Melick Dr, Delaware", "chicago")

    assert result == {
        "status": "error",
        "error_message": "A driving route could not be calculated.",
    }