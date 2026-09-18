# """GreenPulse AI backend: turn a sensor reading into plant-care advice.

# Run locally with:
#     uvicorn main:app --reload
# """

# from __future__ import annotations

# import os
# from datetime import datetime, timezone
# from typing import Literal

# from dotenv import load_dotenv
# from fastapi import FastAPI, HTTPException
# from langchain_core.prompts import ChatPromptTemplate
# from langchain_openai import ChatOpenAI
# from pydantic import BaseModel, Field

# load_dotenv()

# app = FastAPI(title="GreenPulse AI Backend", version="0.1.0")


# class SensorReading(BaseModel):
#     """The MQTT subscriber will later convert its JSON payload into this model."""

#     plant_id: str = Field(default="demo-plant", min_length=1, max_length=80)
#     temperature_c: float = Field(ge=-10, le=60)
#     humidity_percent: float = Field(ge=0, le=100)
#     soil_moisture_percent: float = Field(ge=0, le=100)
#     light_lux: float | None = Field(default=None, ge=0, le=200_000)
#     timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# class CareRecommendation(BaseModel):
#     urgency: Literal["low", "medium", "high"]
#     headline: str = Field(description="A short dashboard-friendly summary")
#     care_message: str = Field(description="Warm, plant-focused recommendation in 2-3 sentences")
#     actions: list[str] = Field(description="One to three practical next steps")
#     reason: str = Field(description="Which sensor values led to the advice")
#     generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# PROMPT = ChatPromptTemplate.from_messages(
#     [
#         (
#             "system",
#             """You are GreenPulse, a careful indoor-plant care assistant. Give useful,
#             conservative advice based only on the supplied sensor data. Do not claim to know
#             the plant species. Treat soil moisture below 25% as potentially urgent, 25-45% as
#             worth monitoring, and values above 45% as usually not needing immediate watering.
#             Do not diagnose plant disease or promise outcomes. Keep every action practical.""",
#         ),
#         ("human", "Sensor data for {plant_id}:\n{reading}"),
#     ]
# )


# def create_care_agent() -> object:
#     """Create the LangChain + OpenAI chain only after configuration is checked."""

#     if not os.getenv("OPENAI_API_KEY"):
#         raise RuntimeError("OPENAI_API_KEY is missing. Add it to the .env file before using /care.")

#     model = os.getenv("OPENAI_MODEL", "gpt-5.6-luna")
#     llm = ChatOpenAI(model=model, temperature=0.2)
#     return PROMPT | llm.with_structured_output(CareRecommendation)


# @app.get("/health")
# def health() -> dict[str, str]:
#     """Safe endpoint for checking that the server is running."""

#     return {"status": "ok", "service": "GreenPulse AI backend"}


# @app.post("/care", response_model=CareRecommendation)
# def generate_care_recommendation(reading: SensorReading) -> CareRecommendation:
#     """Generate one recommendation from a validated live sensor reading."""

#     try:
#         agent = create_care_agent()
#         result = agent.invoke(
#             {
#                 "plant_id": reading.plant_id,
#                 "reading": reading.model_dump_json(indent=2),
#             }
#         )
#         return result
#     except RuntimeError as error:
#         raise HTTPException(status_code=503, detail=str(error)) from error
#     except Exception as error:
#         # Do not expose provider or key details to a dashboard client.
#         raise HTTPException(status_code=502, detail="The AI care service could not generate a recommendation.") from error
import json

from care_agent import care_agent
from weather_agent import get_weather_summary
from logging_config import logger


def load_sensor_data():

    with open("sensor_data.json", "r") as file:
        return json.load(file)


def main():

    print("\n🌱 GREENPULSE AI BACKEND")
    print("=" * 60)

    # =========================================================
    # SENSOR INPUT
    # =========================================================

    sensor_data = load_sensor_data()

    print("\n📥 SENSOR INPUT")

    print(
        json.dumps(
            sensor_data,
            indent=4
        )
    )

    # =========================================================
    # WEATHER AGENT
    # =========================================================

    print("\n🌦️ WEATHER AGENT")
    print("Fetching live weather...")

    weather_data = get_weather_summary()

    print(
        json.dumps(
            weather_data,
            indent=4
        )
    )

    # =========================================================
    # CARE + DECISION AGENTS
    # =========================================================

    print("\n🤖 CARE AGENT")
    print("Combining environment + weather...")

    result = care_agent(
        sensor_data,
        weather_data
    )

    # =========================================================
    # DECISION
    # =========================================================

    print("\n🧠 DECISION RESOLVER")

    print(
        json.dumps(
            result["decision"],
            indent=4
        )
    )

    # =========================================================
    # URGENCY
    # =========================================================

    print("\n🚨 FINAL URGENCY PAYLOAD")

    print(
        json.dumps(
            result["urgency"],
            indent=4
        )
    )

    # =========================================================
    # CARE
    # =========================================================

    print("\n🤖 FINAL CARE PAYLOAD")

    print(
        json.dumps(
            result["care"],
            indent=4
        )
    )

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()