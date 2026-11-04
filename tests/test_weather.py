from pathlib import Path
import json
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ios_control_bridge import weather


class FakeResponse:
    def __init__(self, payload, status=200):
        self.body = json.dumps(payload).encode("utf8")
        self.status = status

    def read(self, size=-1):
        return self.body if size is None or size < 0 else self.body[:size]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


CURRENT_PAYLOAD = {
    "latitude": 52.52, "longitude": 13.41, "timezone": "Europe/Berlin",
    "utc_offset_seconds": 3600,
    "current": {"time": "2026-11-04T12:00", "temperature_2m": 8.4, "relative_humidity_2m": 70,
                "apparent_temperature": 6.1, "is_day": 1, "precipitation": 0.0,
                "weather_code": 3, "wind_speed_10m": 12.0},
}
FORECAST_PAYLOAD = {
    "timezone": "Europe/Berlin", "utc_offset_seconds": 3600,
    "daily": {"time": ["2026-11-04", "2026-11-05", "2026-11-06"],
              "weather_code": [3, 61, 0],
              "temperature_2m_max": [10.0, 9.0, 11.0],
              "temperature_2m_min": [4.0, 3.0, 5.0],
              "precipitation_probability_max": [10, 80, 0],
              "sunrise": ["2026-11-04T07:00", "2026-11-05T07:01", "2026-11-06T07:02"],
              "sunset": ["2026-11-04T16:30", "2026-11-05T16:29", "2026-11-06T16:28"]},
}


class WeatherBoundaryTests(unittest.TestCase):
    def test_current_requires_explicit_coordinates(self):
        self.assertEqual(weather.current({})["reason"], "invalid_location")
        self.assertEqual(weather.current({"latitude": 52.52})["reason"], "invalid_location")
        self.assertEqual(weather.current({"latitude": 91, "longitude": 0})["reason"], "invalid_location")

    def test_current_returns_provider_attribution(self):
        with patch("urllib.request.urlopen", return_value=FakeResponse(CURRENT_PAYLOAD)):
            output = weather.current({"latitude": 52.52, "longitude": 13.41})
        self.assertEqual(output["status"], "verified")
        self.assertEqual(output["data"]["provider"], "Open-Meteo")
        self.assertEqual(output["data"]["current"]["weather"], "Overcast")
        self.assertEqual(output["data"]["units"], "metric")

    def test_imperial_units_change_request(self):
        with patch("urllib.request.urlopen", return_value=FakeResponse(CURRENT_PAYLOAD)) as call:
            weather.current({"latitude": 52.52, "longitude": 13.41, "units": "imperial"})
        request_url = call.call_args.args[0].full_url
        self.assertIn("temperature_unit=fahrenheit", request_url)
        self.assertIn("wind_speed_unit=mph", request_url)

    def test_forecast_requires_bounded_days(self):
        self.assertEqual(weather.forecast({"latitude": 1, "longitude": 1, "days": 0})["reason"], "invalid_days")
        self.assertEqual(weather.forecast({"latitude": 1, "longitude": 1, "days": 8})["reason"], "invalid_days")

    def test_forecast_rows(self):
        with patch("urllib.request.urlopen", return_value=FakeResponse(FORECAST_PAYLOAD)):
            output = weather.forecast({"latitude": 52.52, "longitude": 13.41, "days": 2})
        self.assertEqual(output["status"], "verified")
        self.assertEqual(len(output["data"]["daily"]), 2)
        self.assertEqual(output["data"]["daily"][1]["weather"], "Slight rain")

    def test_network_error(self):
        import urllib.error
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("offline")):
            output = weather.current({"latitude": 1, "longitude": 1})
        self.assertEqual(output["status"], "unavailable")
        self.assertEqual(output["reason"], "network_error")


if __name__ == "__main__":
    unittest.main()
