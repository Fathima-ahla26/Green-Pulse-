import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI

from decision_agent import resolve_decision
from gmail_agent import get_inbox_summary


load_dotenv()


# ============================================================
# CONFIGURATION
# ============================================================

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

GEMINI_MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-3.5-flash"
)


# ============================================================
# STRUCTURED GEMINI OUTPUT
# ============================================================

class CareAIOutput(BaseModel):

    quote: str = Field(
        description=(
            "A short creative literature-style quote that "
            "is specifically inspired by the named plant "
            "and its current environmental condition."
        )
    )

    care_tip: str = Field(
        description=(
            "Practical, plant-specific care advice based "
            "on sensor readings, weather, environmental "
            "decision and relevant gardening emails."
        )
    )


# ============================================================
# GEMINI MODEL
# ============================================================

def create_model():

    if not GEMINI_API_KEY:

        raise ValueError(
            "GEMINI_API_KEY is missing from .env"
        )

    return ChatGoogleGenerativeAI(
        model=GEMINI_MODEL,
        google_api_key=GEMINI_API_KEY,
        temperature=0.4
    )


# ============================================================
# SENSOR DATA NORMALIZATION
# ============================================================

def normalize_sensor_data(sensor_data: dict) -> dict:
    """
    Supports both:

    1. Real MQTT telemetry contract
    2. Earlier local mock sensor format
    """

    readings = sensor_data.get(
        "readings",
        {}
    )

    plant = sensor_data.get(
        "plant",
        "Unknown plant"
    )

    if readings:

        return {
            "device_id": sensor_data.get(
                "device_id",
                "greenpulse-01"
            ),

            "plant": plant,

            "seq": sensor_data.get(
                "seq"
            ),

            "ts": sensor_data.get(
                "ts"
            ),

            "soil_moisture_pct": readings.get(
                "soil_moisture_pct"
            ),

            "soil_raw": readings.get(
                "soil_raw"
            ),

            "temperature_c": readings.get(
                "temperature_c"
            ),

            "humidity_pct": readings.get(
                "humidity_pct"
            )
        }

    # --------------------------------------------------------
    # Backward compatibility with sensor_data.json
    # --------------------------------------------------------

    return {
        "device_id": sensor_data.get(
            "device_id",
            "greenpulse-01"
        ),

        "plant": plant,

        "seq": sensor_data.get(
            "seq"
        ),

        "ts": sensor_data.get(
            "ts"
        ),

        "soil_moisture_pct": sensor_data.get(
            "soil_moisture"
        ),

        "soil_raw": sensor_data.get(
            "soil_raw"
        ),

        "temperature_c": sensor_data.get(
            "temperature"
        ),

        "humidity_pct": sensor_data.get(
            "humidity"
        )
    }


# ============================================================
# TIMESTAMP
# ============================================================

def get_timestamp(sensor_data: dict) -> str:
    """
    Use the device timestamp when available.
    Otherwise generate a UTC timestamp.
    """

    ts = sensor_data.get("ts")

    if ts:
        return ts

    return (
        datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


# ============================================================
# WEATHER SUMMARY BUILDER
# ============================================================

def build_rich_weather_summary(
    weather_data: dict
) -> str:
    """
    Convert the structured weather-agent output into a
    concise, context-rich summary suitable for the MQTT
    care payload and Node-RED dashboard.
    """

    location = weather_data.get(
        "location",
        "Plant location"
    )

    temperature = weather_data.get(
        "temperature_c"
    )

    humidity = weather_data.get(
        "humidity_pct"
    )

    condition = weather_data.get(
        "weather_condition",
        "Weather information unavailable"
    )

    rain_probability = weather_data.get(
        "max_rain_probability_pct"
    )

    next_12h_rain = weather_data.get(
        "next_12h_rain_mm"
    )

    current_rain = weather_data.get(
        "current_rain_mm"
    )

    # --------------------------------------------------------
    # Build readable values
    # --------------------------------------------------------

    temperature_text = (
        f"{temperature:.1f}°C"
        if isinstance(temperature, (int, float))
        else "unavailable"
    )

    humidity_text = (
        f"{humidity:.0f}%"
        if isinstance(humidity, (int, float))
        else "unavailable"
    )

    probability_text = (
        f"{rain_probability:.0f}%"
        if isinstance(rain_probability, (int, float))
        else "unavailable"
    )

    rain_text = (
        f"{next_12h_rain:.1f} mm"
        if isinstance(next_12h_rain, (int, float))
        else "unavailable"
    )

    current_rain_text = (
        f"{current_rain:.1f} mm"
        if isinstance(current_rain, (int, float))
        else "unavailable"
    )

    return (
        f"{location}: {condition}, "
        f"{temperature_text} and {humidity_text} humidity. "
        f"Current rain is {current_rain_text}. "
        f"Rain probability over the forecast period is "
        f"{probability_text}, with approximately "
        f"{rain_text} expected in the next 12 hours."
    )


# ============================================================
# CARE AGENT
# ============================================================

def generate_care_response(
    sensor_data: dict,
    weather_data: dict
) -> dict:

    normalized = normalize_sensor_data(
        sensor_data
    )

    # --------------------------------------------------------
    # 1. Environmental decision
    # --------------------------------------------------------

    decision = resolve_decision(
        sensor_data,
        weather_data
    )

    # --------------------------------------------------------
    # 2. Gmail Inbox Agent
    # --------------------------------------------------------

    print("\n📧 Calling Inbox Agent...")

    inbox_summary = get_inbox_summary()

    print(
        f"📨 Inbox information: {inbox_summary}"
    )

    # --------------------------------------------------------
    # 3. Rich weather summary
    # --------------------------------------------------------

    weather_summary = build_rich_weather_summary(
        weather_data
    )

    print(
        f"🌦️ Weather summary: {weather_summary}"
    )

    # --------------------------------------------------------
    # 4. Gemini prompt
    # --------------------------------------------------------

    prompt = f"""
You are the GreenPulse Care Agent.

GreenPulse is an intelligent IoT plant-care system.

Your task is to generate:

1. A short, creative, literature-style quote inspired
   specifically by the named plant and its current
   environmental condition.

2. Practical, context-aware, plant-specific care advice.

--------------------------------------------------
IMPORTANT REQUIREMENTS
--------------------------------------------------

PLANT-SPECIFIC GENERATION:

The plant name is:

{normalized["plant"]}

Use this plant identity naturally in the advice
when appropriate.

The quote should be inspired by the actual plant,
its current condition, and the surrounding environment.

Do not produce a generic quote that could apply to
any plant.

The care tip should also refer to the plant specifically
when useful.

--------------------------------------------------
ENVIRONMENTAL REASONING
--------------------------------------------------

Respect the final environmental decision.

Do NOT contradict the final urgency decision.

Soil moisture is the primary indicator of whether
watering may be needed.

Weather is supporting information.

If soil is dry but significant rain is expected,
do not blindly recommend heavy watering.

If a gardening email recommends watering but weather
indicates substantial imminent rainfall, explain the
situation and follow the environmental decision.

Do not invent weather information.

Do not invent email information.

Do not diagnose diseases.

Do not make unsupported claims about plant health.

--------------------------------------------------
QUOTE REQUIREMENTS
--------------------------------------------------

Create a short literary-style quote.

The quote should:

- relate to the named plant
- reflect its current environmental condition
- be creative but natural
- avoid clichés
- normally be one sentence

--------------------------------------------------
CARE TIP REQUIREMENTS
--------------------------------------------------

Create practical advice based on:

- plant identity
- soil moisture
- temperature
- humidity
- weather
- rainfall forecast
- relevant gardening email information
- final watering decision

Keep it concise, normally 1-3 sentences.

--------------------------------------------------
PLANT
--------------------------------------------------

Plant:
{normalized["plant"]}

--------------------------------------------------
SENSOR DATA
--------------------------------------------------

Device:
{normalized["device_id"]}

Soil moisture:
{normalized["soil_moisture_pct"]} %

Raw soil reading:
{normalized["soil_raw"]}

Temperature:
{normalized["temperature_c"]} °C

Humidity:
{normalized["humidity_pct"]} %

--------------------------------------------------
FINAL ENVIRONMENTAL DECISION
--------------------------------------------------

Urgency:
{decision["level"]}

Score:
{decision["score"]}

Next watering ETA:
{decision["next_water_eta_hours"]} hours

Reason:
{decision["reason"]}

--------------------------------------------------
WEATHER INFORMATION
--------------------------------------------------

{weather_summary}

--------------------------------------------------
GARDENING / NOTIFICATION INFORMATION
--------------------------------------------------

{inbox_summary}

--------------------------------------------------
FINAL INSTRUCTION
--------------------------------------------------

Generate ONLY the structured fields:

quote
care_tip
"""

    # --------------------------------------------------------
    # 5. Gemini
    # --------------------------------------------------------

    model = create_model()

    structured_model = model.with_structured_output(
        CareAIOutput,
        method="json_schema"
    )

    result = structured_model.invoke(
        prompt
    )

    # --------------------------------------------------------
    # 6. Timestamp
    # --------------------------------------------------------

    timestamp = get_timestamp(
        sensor_data
    )

    # --------------------------------------------------------
    # 7. MQTT urgency payload
    # --------------------------------------------------------

    urgency_payload = {
        "device_id": normalized["device_id"],
        "ts": timestamp,
        "in_reply_to": normalized["seq"],
        "level": decision["level"],
        "score": decision["score"],
        "next_water_eta_hours": decision[
            "next_water_eta_hours"
        ]
    }

    # --------------------------------------------------------
    # 8. MQTT care payload
    # --------------------------------------------------------

    care_payload = {
        "device_id": normalized["device_id"],
        "ts": timestamp,
        "in_reply_to": normalized["seq"],
        "quote": result.quote.strip(),
        "care_tip": result.care_tip.strip(),
        "weather_summary": weather_summary,
        "inbox_summary": inbox_summary,
        "agents": [
            "environment",
            "weather",
            "inbox"
        ],
        "model": GEMINI_MODEL
    }

    return {
        "decision": decision,
        "urgency": urgency_payload,
        "care": care_payload
    }


# ============================================================
# PUBLIC FUNCTION USED BY MQTT BACKEND
# ============================================================

def care_agent(
    sensor_data: dict,
    weather_data: dict
) -> dict:

    return generate_care_response(
        sensor_data,
        weather_data
    )


# ============================================================
# LOCAL TEST
# ============================================================

if __name__ == "__main__":

    print("\n🌱 GREENPULSE CARE AGENT")
    print("=" * 50)

    test_sensor = {
        "device_id": "greenpulse-01",
        "plant": "Tomato",
        "seq": 1482,
        "ts": (
            datetime.now(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        ),
        "readings": {
            "soil_moisture_pct": 18,
            "soil_raw": 2210,
            "temperature_c": 31.5,
            "humidity_pct": 55
        }
    }

    test_weather = {
        "location": "Malabe",
        "temperature_c": 25.1,
        "humidity_pct": 97,
        "current_rain_mm": 0.1,
        "current_precipitation_mm": 0.1,
        "weather_condition": "Light drizzle",
        "max_rain_probability_pct": 100,
        "next_12h_rain_mm": 5.2,
        "next_12h_precipitation_mm": 7.2,
        "rain_expected": True,
        "summary": (
            "Malabe: Light drizzle, 25.1°C and 97% humidity. "
            "Rain is expected within the next several hours."
        )
    }

    result = care_agent(
        test_sensor,
        test_weather
    )

    print("\n🧠 DECISION:")
    print(result["decision"])

    print("\n🚨 FINAL URGENCY PAYLOAD:")
    print(result["urgency"])

    print("\n🤖 FINAL CARE PAYLOAD:")
    print(result["care"])

    print("\n" + "=" * 60)