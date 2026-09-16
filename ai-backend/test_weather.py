from weather_agent import get_weather_summary


result = get_weather_summary()

print("\n🌱 GREENPULSE WEATHER TEST")
print("=" * 60)

for key, value in result.items():
    print(f"{key}: {value}")

print("=" * 60)