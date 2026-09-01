from zoo_travel_mcp_server import server


def test_get_zoo_weather_returns_current_conditions(monkeypatch):
    monkeypatch.setattr(
        server,
        "fetch_json",
        lambda url: {
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

    conditions = server.get_zoo_weather()

    assert conditions["status"] == "success"
    assert conditions["temperature_c"] == 22.5
    assert conditions["source"] == "Open-Meteo"


def test_get_weather_forecast_limits_results_to_requested_days(monkeypatch):
    monkeypatch.setattr(
        server,
        "fetch_json",
        lambda url: {
            "daily": {
                "time": ["2026-08-31", "2026-09-01"],
                "weather_code": [1, 3],
                "temperature_2m_min": [16, 14],
                "temperature_2m_max": [25, 22],
                "precipitation_probability_max": [10, 40],
            }
        },
    )

    forecast = server.get_weather_forecast(days=2)

    assert forecast["status"] == "success"
    assert [day["date"] for day in forecast["forecast"]] == [
        "2026-08-31",
        "2026-09-01",
    ]


def test_get_weather_forecast_rejects_invalid_day_count():
    result = server.get_weather_forecast(days=8)

    assert result == {
        "status": "error",
        "error_message": "Forecast days must be between 1 and 7.",
    }


def test_get_zoo_weather_reports_provider_failures(monkeypatch):
    def unavailable(url):
        raise RuntimeError("Travel conditions provider is unavailable.")

    monkeypatch.setattr(server, "fetch_json", unavailable)

    result = server.get_zoo_weather()

    assert result == {
        "status": "error",
        "error_message": "Travel conditions provider is unavailable.",
    }


def test_route_and_traffic_are_explicitly_unavailable_without_a_provider():
    route = server.get_route_to_zoo("Union Station")
    traffic = server.get_traffic_conditions("Union Station")

    assert route["status"] == "unavailable"
    assert traffic["status"] == "unavailable"


def test_route_requires_an_origin():
    result = server.get_route_to_zoo(" ")

    assert result == {
        "status": "error",
        "error_message": "An origin is required for route planning.",
    }