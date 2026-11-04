"""Weather queries against an explicit provider; no cached data is presented as current."""
import json
import math
import urllib.error
import urllib.parse
import urllib.request

from .result import result

PROVIDER = "Open-Meteo"
PROVIDER_URL = "https://open-meteo.com/"
ENDPOINT = "https://api.open-meteo.com/v1/forecast"
WEATHER_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Depositing rime fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    56: "Light freezing drizzle", 57: "Dense freezing drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    66: "Light freezing rain", 67: "Heavy freezing rain",
    71: "Slight snow fall", 73: "Moderate snow fall", 75: "Heavy snow fall",
    77: "Snow grains",
    80: "Slight rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
    85: "Slight snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with slight hail", 99: "Thunderstorm with heavy hail",
}
IMPERIAL = {"temperature": "fahrenheit", "wind": "mph", "precipitation": "inch"}


def _number(params, key, minimum, maximum):
    value = params.get(key)
    if type(value) not in (int, float) or not math.isfinite(value):
        return None
    if not minimum <= value <= maximum:
        return None
    return float(value)


def _options(params, allowed):
    extra = set(params) - set(allowed)
    if extra:
        return None, result("weather", "error", reason="unknown_parameters",
                            data={"unknown": sorted(extra)})
    latitude = _number(params, "latitude", -90.0, 90.0)
    longitude = _number(params, "longitude", -180.0, 180.0)
    if latitude is None or longitude is None:
        return None, result("weather", "error", reason="invalid_location")
    units = params.get("units", "metric")
    if units not in ("metric", "imperial"):
        return None, result("weather", "error", reason="invalid_units")
    timezone = params.get("timezone", "auto")
    if not isinstance(timezone, str) or not 1 <= len(timezone) <= 64:
        return None, result("weather", "error", reason="invalid_timezone")
    return {"latitude": latitude, "longitude": longitude, "units": units,
            "timezone": timezone}, None


def _request(params, extra, request_id):
    query = {
        "latitude": format(params["latitude"], ".6f"),
        "longitude": format(params["longitude"], ".6f"),
        "timezone": params["timezone"],
    }
    query.update(extra)
    if params["units"] == "imperial":
        query["temperature_unit"] = IMPERIAL["temperature"]
        query["wind_speed_unit"] = IMPERIAL["wind"]
        query["precipitation_unit"] = IMPERIAL["precipitation"]
    url = ENDPOINT + "?" + urllib.parse.urlencode(query)
    request = urllib.request.Request(url, headers={"User-Agent": "ios-control-bridge/0.5"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read(1024 * 1024 + 1)
            status = response.status
    except urllib.error.HTTPError as error:
        return None, result("weather", "unavailable", reason="provider_http_error",
                            data={"status": error.code}, request_id=request_id)
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        return None, result("weather", "unavailable", reason="network_error",
                            data={"error": str(error)[:300]}, request_id=request_id)
    if status != 200:
        return None, result("weather", "unavailable", reason="provider_status",
                            data={"status": status}, request_id=request_id)
    if len(body) > 1024 * 1024:
        return None, result("weather", "partial", reason="provider_response_limit", request_id=request_id)
    try:
        payload = json.loads(body)
    except (TypeError, ValueError):
        return None, result("weather", "error", reason="invalid_provider_json", request_id=request_id)
    if not isinstance(payload, dict):
        return None, result("weather", "error", reason="invalid_provider_json", request_id=request_id)
    payload["_request_url"] = url
    return payload, None


def _quality(payload, request_id):
    if "error" in payload:
        return result("weather", "unavailable", reason="provider_error",
                      data={"provider_error": str(payload.get("error"))[:300]}, request_id=request_id)
    if "current" not in payload and "daily" not in payload:
        return result("weather", "error", reason="provider_missing_fields", request_id=request_id)
    return None


def current(params, request_id=None):
    operation = "weather.current"
    options, failure = _options(params, ("latitude", "longitude", "units", "timezone"))
    if failure:
        failure["operation"] = operation
        return failure
    payload, failure = _request(options, {
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,"
                   "is_day,precipitation,weather_code,wind_speed_10m",
    }, request_id)
    if failure:
        failure["operation"] = operation
        return failure
    failure = _quality(payload, request_id)
    if failure:
        failure["operation"] = operation
        return failure
    current = payload.get("current")
    if not isinstance(current, dict):
        return result(operation, "error", reason="provider_missing_current", request_id=request_id)
    record = dict(current)
    code = record.get("weather_code")
    if type(code) is int:
        record["weather"] = WEATHER_CODES.get(code, "Unknown")
    return result(operation, "verified", request_id=request_id, complete=True,
                  data={"provider": PROVIDER, "attribution": PROVIDER_URL,
                        "requested": options, "units": options["units"],
                        "timezone": payload.get("timezone"),
                        "utc_offset_seconds": payload.get("utc_offset_seconds"),
                        "current": record, "source_url": payload.get("_request_url")},
                  source=PROVIDER)


def forecast(params, request_id=None):
    operation = "weather.forecast"
    days = params.get("days", 3)
    if type(days) is not int or not 1 <= days <= 7:
        return result(operation, "error", reason="invalid_days", request_id=request_id)
    options, failure = _options(params, ("latitude", "longitude", "units", "timezone", "days"))
    if failure:
        failure["operation"] = operation
        return failure
    payload, failure = _request(options, {
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,"
                 "precipitation_probability_max,sunrise,sunset",
        "forecast_days": str(days),
    }, request_id)
    if failure:
        failure["operation"] = operation
        return failure
    failure = _quality(payload, request_id)
    if failure:
        failure["operation"] = operation
        return failure
    daily = payload.get("daily")
    if not isinstance(daily, dict):
        return result(operation, "error", reason="provider_missing_daily", request_id=request_id)
    dates = daily.get("time") if isinstance(daily.get("time"), list) else []
    rows = []
    for index, date in enumerate(dates[:days]):
        row = {"date": date}
        for key in ("weather_code", "temperature_2m_max", "temperature_2m_min",
                    "precipitation_probability_max", "sunrise", "sunset"):
            values = daily.get(key)
            if isinstance(values, list) and index < len(values):
                row[key] = values[index]
        if type(row.get("weather_code")) is int:
            row["weather"] = WEATHER_CODES.get(row["weather_code"], "Unknown")
        rows.append(row)
    return result(operation, "verified", request_id=request_id, complete=len(rows) == days,
                  data={"provider": PROVIDER, "attribution": PROVIDER_URL,
                        "requested": options, "days": days, "units": options["units"],
                        "timezone": payload.get("timezone"),
                        "utc_offset_seconds": payload.get("utc_offset_seconds"),
                        "daily": rows, "source_url": payload.get("_request_url")},
                  source=PROVIDER)
