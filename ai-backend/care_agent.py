import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()


class CareAIOutput(BaseModel):
    quote: str = Field(
        description="A short, memorable plant-care quote."
    )
    care_tip: str = Field(
        description="A practical 1-3 sentence recommendation."
    )


def create_gemini_model():
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is missing from the .env file."
        )

    model_name = os.getenv(
        "GEMINI_MODEL",
        "gemini-3.6-flash"
    )

    model = ChatGoogleGenerativeAI(
        model=model_name,
        max_retries=2
    )

    return model


def normalize_sensor_data(sensor_data):
    """
    Supports both:
    1. GreenPulse MQTT telemetry format
    2. Local test sensor_data.json format
    """

    if "readings" in sensor_data:

        readings = sensor_data["readings"]

        return {
            "device_id": sensor_data.get(
                "device_id",
                "greenpulse-01"
            ),
            "seq": sensor_data.get("seq"),
            "ts": sensor_data.get("ts"),
            "plant": sensor_data.get(
                "plant",
                "Unknown"
            ),
            "soil_moisture": readings.get(
                "soil_moisture_pct"
            ),
            "soil_raw": readings.get(
                "soil_raw"
            ),
            "temperature": readings.get(
                "temperature_c"
            ),
            "humidity": readings.get(
                "humidity_pct"
            )
        }

    return {
        "device_id": sensor_data.get(
            "device_id",
            "greenpulse-01"
        ),
        "seq": sensor_data.get("seq"),
        "ts": sensor_data.get("ts"),
        "plant": sensor_data.get(
            "plant",
            "Unknown"
        ),
        "soil_moisture": sensor_data.get(
            "soil_moisture"
        ),
        "soil_raw": sensor_data.get(
            "soil_raw"
        ),
        "temperature": sensor_data.get(
            "temperature"
        ),
        "humidity": sensor_data.get(
            "humidity"
        )
    }


def calculate_urgency(soil_moisture):
    """
    Initial environment-based urgency.

    Weather is considered later by the AI care decision.
    """

    if soil_moisture is None:
        return {
            "level": "amber",
            "score": 0.5,
            "next_water_eta_hours": None
        }

    if soil_moisture < 20:

        return {
            "level": "red",
            "score": 0.90,
            "next_water_eta_hours": 2.0
        }

    elif soil_moisture < 35:

        return {
            "level": "amber",
            "score": 0.62,
            "next_water_eta_hours": 12.0
        }

    else:

        return {
            "level": "green",
            "score": 0.20,
            "next_water_eta_hours": None
        }


def care_agent(sensor_data, weather_data=None):

    data = normalize_sensor_data(sensor_data)

    plant = data["plant"]
    soil_moisture = data["soil_moisture"]
    temperature = data["temperature"]
    humidity = data["humidity"]

    if soil_moisture is None:
        raise ValueError(
            "soil_moisture_pct is missing from the sensor reading."
        )

    urgency = calculate_urgency(
        soil_moisture
    )

    # ---------------------------------------------------------
    # WEATHER INFORMATION
    # ---------------------------------------------------------

    if weather_data:

        weather_location = weather_data.get(
            "location",
            "Unknown"
        )

        weather_temperature = weather_data.get(
            "temperature_c"
        )

        weather_humidity = weather_data.get(
            "humidity_pct"
        )

        weather_condition = weather_data.get(
            "weather_condition",
            "Unknown"
        )

        rain_probability = weather_data.get(
            "max_rain_probability_pct"
        )

        next_12h_rain = weather_data.get(
            "next_12h_rain_mm"
        )

        rain_expected = weather_data.get(
            "rain_expected",
            False
        )

        weather_summary = weather_data.get(
            "summary",
            ""
        )

    else:

        weather_location = "Unknown"
        weather_temperature = None
        weather_humidity = None
        weather_condition = "Unknown"
        rain_probability = None
        next_12h_rain = None
        rain_expected = False
        weather_summary = ""

    # ---------------------------------------------------------
    # AI PROMPT
    # ---------------------------------------------------------

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                """
You are the GreenPulse plant-care AI.

You receive information from multiple agents:

1. ENVIRONMENT AGENT
   - Soil moisture
   - Temperature
   - Humidity

2. WEATHER AGENT
   - Current weather
   - Rain probability
   - Expected rainfall

Your job is to combine these sources and produce
one practical plant-care recommendation.

IMPORTANT DECISION RULES:

1. Soil moisture is the primary indicator of whether
   the plant currently needs water.

2. Weather is supporting information.

3. If the soil is very dry but significant rain is
   expected soon, consider whether immediate watering
   can be reduced or delayed.

4. If the soil is very dry and no significant rain
   is expected, clearly recommend watering.

5. If soil moisture is healthy and rain is expected,
   do not recommend unnecessary watering.

6. Do not invent weather information.

7. Do not invent email information.

8. Use only the supplied sensor and weather data.

9. Give practical and conservative advice.

10. Do not diagnose plant diseases.

11. Return only the requested structured fields.

12. The quote should be short and memorable.

13. The care tip should be 1-3 sentences.

This is a multi-agent decision system.
The final recommendation must consider BOTH
environment data and weather data.
"""
            ),
            (
                "human",
                """
PLANT INFORMATION
Plant: {plant}

ENVIRONMENT AGENT
Soil moisture: {soil_moisture}%
Temperature: {temperature}°C
Humidity: {humidity}%

WEATHER AGENT
Location: {weather_location}
Weather: {weather_condition}
Weather temperature: {weather_temperature}°C
Weather humidity: {weather_humidity}%
Maximum rain probability: {rain_probability}%
Expected rain in next 12 hours: {next_12h_rain} mm
Rain expected: {rain_expected}

Weather summary:
{weather_summary}

Generate the final GreenPulse plant-care recommendation.
"""
            )
        ]
    )

    model = create_gemini_model()

    structured_model = model.with_structured_output(
        CareAIOutput,
        method="json_schema"
    )

    chain = prompt | structured_model

    result = chain.invoke(
        {
            "plant": plant,
            "soil_moisture": soil_moisture,
            "temperature": temperature,
            "humidity": humidity,
            "weather_location": weather_location,
            "weather_condition": weather_condition,
            "weather_temperature": weather_temperature,
            "weather_humidity": weather_humidity,
            "rain_probability": rain_probability,
            "next_12h_rain": next_12h_rain,
            "rain_expected": rain_expected,
            "weather_summary": weather_summary
        }
    )

    # ---------------------------------------------------------
    # TIMESTAMP
    # ---------------------------------------------------------

    timestamp = data["ts"]

    if not timestamp:

        timestamp = (
            datetime.now(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )

    # ---------------------------------------------------------
    # CARE MQTT PAYLOAD
    # ---------------------------------------------------------

    care_payload = {
        "device_id": data["device_id"],
        "ts": timestamp,
        "in_reply_to": data["seq"],
        "quote": result.quote,
        "care_tip": result.care_tip,
        "weather_summary": weather_summary,
        "inbox_summary": "",
        "agents": [
            "environment",
            "weather"
        ],
        "model": os.getenv(
            "GEMINI_MODEL",
            "gemini-3.6-flash"
        )
    }

    # ---------------------------------------------------------
    # URGENCY MQTT PAYLOAD
    # ---------------------------------------------------------

    urgency_payload = {
        "device_id": data["device_id"],
        "ts": timestamp,
        "in_reply_to": data["seq"],
        "level": urgency["level"],
        "score": urgency["score"],
        "next_water_eta_hours": (
            urgency["next_water_eta_hours"]
        )
    }

    return {
        "urgency": urgency_payload,
        "care": care_payload
    }