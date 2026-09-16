# GreenPulse AI Backend — Person C, Milestone 1

This is the first building block of the AI backend: validated sensor data in, an
LLM-generated care recommendation out. MQTT, weather, and Gmail will attach to
this working core in later milestones.

## 1. Install the libraries

In the `ai-backend` folder, activate your virtual environment and install:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## 2. Add your API key

Copy the variable names from `.env.example` into `.env`, then replace the API-key
placeholder with your own key. Keep `.env` private: it is already excluded by
`.gitignore`.

## 3. Start the server

```powershell
uvicorn main:app --reload
```

Open `http://127.0.0.1:8000/docs` in a browser. Use **POST /care**, select **Try
it out**, and send this sample body:

```json
{
  "plant_id": "living-room-fern",
  "temperature_c": 30.2,
  "humidity_percent": 42,
  "soil_moisture_percent": 18,
  "light_lux": 850
}
```

You should receive an urgency level, a care message, actions, and the reason for
the advice. Screenshot that response for your demonstration.

## Next milestones

1. Add an MQTT subscriber that receives Person B's agreed sensor JSON and calls
   `generate_care_recommendation`.
2. Publish the recommendation to the agreed care topic for Node-RED.
3. Add weather data to the input.
4. Add Gmail OAuth and a summariser for watering or weather-alert emails.
5. Deploy this same service to a cloud server.

## Topic proposal for the group

Agree these exact names with Person A, B, and D before coding MQTT:

| Direction | Topic |
| --- | --- |
| ESP32 to backend | `greenpulse/{plant_id}/sensor` |
| Backend to dashboard/device | `greenpulse/{plant_id}/care` |
| Backend status | `greenpulse/{plant_id}/status` |

Suggested sensor payload:

```json
{
  "plant_id": "living-room-fern",
  "temperature_c": 30.2,
  "humidity_percent": 42,
  "soil_moisture_percent": 18,
  "light_lux": 850,
  "timestamp": "2026-09-11T09:30:00Z"
}
```
