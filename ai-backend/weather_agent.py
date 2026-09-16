import os
from datetime import datetime

import requests
from dotenv import load_dotenv

load_dotenv()


WEATHER_API_URL = "https://api.open-meteo.com/v1/forecast"

LATITUDE = float(os.getenv("PLANT_LATITUDE", "6.9271"))
LONGITUDE = float(os.getenv("PLANT_LONGITUDE", "79.8612"))
LOCATION = os.getenv("PLANT_LOCATION", "Colombo")


def get_weather():

    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "current": (
            "temperature_2m,"
            "relative_humidity_2m,"
            "precipitation,"
            "rain,"
            "weather_code"
        ),
        "hourly": (
            "temperature_2m,"
            "relative_humidity_2m,"
            "precipitation_probability,"
            "precipitation,"
            "rain"
        ),
        "forecast_hours": 12,
        "timezone": "auto"
    }

    response = requests.get(
        WEATHER_API_URL,
        params=params,
        timeout=15
    )

    response.raise_for_status()

    return response.json()


def weather_code_to_text(code):

    weather_codes = {
        0: "Clear sky",
        1: "Mainly clear",
        2: "Partly cloudy",
        3: "Overcast",
        45: "Fog",
        48: "Depositing rime fog",
        51: "Light drizzle",
        53: "Moderate drizzle",
        55: "Dense drizzle",
        61: "Slight rain",
        63: "Moderate rain",
        65: "Heavy rain",
        71: "Slight snow",
        73: "Moderate snow",
        75: "Heavy snow",
        80: "Slight rain showers",
        81: "Moderate rain showers",
        82: "Violent rain showers",
        95: "Thunderstorm",
        96: "Thunderstorm with slight hail",
        99: "Thunderstorm with heavy hail"
    }

    return weather_codes.get(
        code,
        "Unknown weather condition"
    )


def summarize_weather(weather):

    current = weather["current"]
    hourly = weather["hourly"]

    current_temperature = current["temperature_2m"]
    current_humidity = current["relative_humidity_2m"]
    current_rain = current["rain"]
    current_precipitation = current["precipitation"]
    current_code = current["weather_code"]

    precipitation_probabilities = (
        hourly["precipitation_probability"]
    )

    precipitation_values = hourly["precipitation"]
    rain_values = hourly["rain"]

    max_rain_probability = max(
        precipitation_probabilities
    )

    total_upcoming_rain = sum(
        value or 0
        for value in rain_values
    )

    total_upcoming_precipitation = sum(
        value or 0
        for value in precipitation_values
    )

    rain_expected = (
        max_rain_probability >= 50
        or total_upcoming_rain >= 1.0
    )

    if rain_expected:
        rain_advice = (
            "Rain is expected within the next several hours."
        )
    else:
        rain_advice = (
            "No significant rain is currently expected "
            "within the next several hours."
        )

    condition = weather_code_to_text(current_code)

    summary = (
        f"{LOCATION}: {condition}, "
        f"{current_temperature}°C and "
        f"{current_humidity}% humidity. "
        f"{rain_advice}"
    )

    return {
        "location": LOCATION,
        "temperature_c": current_temperature,
        "humidity_pct": current_humidity,
        "current_rain_mm": current_rain,
        "current_precipitation_mm": current_precipitation,
        "weather_condition": condition,
        "max_rain_probability_pct": max_rain_probability,
        "next_12h_rain_mm": round(total_upcoming_rain, 2),
        "next_12h_precipitation_mm": round(
            total_upcoming_precipitation,
            2
        ),
        "rain_expected": rain_expected,
        "summary": summary,
        "retrieved_at": datetime.now().isoformat()
    }


def get_weather_summary():

    weather = get_weather()

    return summarize_weather(weather)


if __name__ == "__main__":

    print("\n🌦️ GREENPULSE WEATHER AGENT")
    print("=" * 60)

    result = get_weather_summary()

    for key, value in result.items():
        print(f"{key}: {value}")

    print("=" * 60)