import json

from decision_agent import resolve_decision
from weather_agent import get_weather_summary


sensor_data = {
    "plant": "Tomato",
    "soil_moisture": 18,
    "temperature": 31.5,
    "humidity": 55
}


print("\n🌱 GREENPULSE DECISION RESOLVER")
print("=" * 60)

print("\n🌦️ Getting live weather...")

weather_data = get_weather_summary()

print("\n📊 WEATHER")
print(json.dumps(
    weather_data,
    indent=4
))

print("\n🧠 RESOLVING ENVIRONMENT + WEATHER...")

decision = resolve_decision(
    sensor_data,
    weather_data
)

print("\n🚨 FINAL DECISION")
print(json.dumps(
    decision,
    indent=4
))

print("=" * 60)