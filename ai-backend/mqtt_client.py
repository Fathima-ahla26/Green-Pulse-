import json
import os
import ssl

import paho.mqtt.client as mqtt
from dotenv import load_dotenv

from care_agent import care_agent

load_dotenv()


AWS_IOT_ENDPOINT = os.getenv("AWS_IOT_ENDPOINT")
AWS_IOT_PORT = int(os.getenv("AWS_IOT_PORT", "8883"))
AWS_IOT_CLIENT_ID = os.getenv("AWS_IOT_CLIENT_ID", "greenpulse-backend")

CA_CERT = os.getenv("AWS_IOT_CA_CERT")
CLIENT_CERT = os.getenv("AWS_IOT_CLIENT_CERT")
PRIVATE_KEY = os.getenv("AWS_IOT_PRIVATE_KEY")

TELEMETRY_TOPIC = os.getenv(
    "MQTT_TELEMETRY_TOPIC",
    "greenpulse/+/telemetry"
)

STATUS_TOPIC = os.getenv(
    "MQTT_STATUS_TOPIC",
    "greenpulse/+/status"
)

URGENCY_TOPIC = os.getenv(
    "MQTT_URGENCY_TOPIC",
    "greenpulse/greenpulse-01/urgency"
)

CARE_TOPIC = os.getenv(
    "MQTT_CARE_TOPIC",
    "greenpulse/greenpulse-01/care"
)


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print("✅ Connected to AWS IoT Core")

        client.subscribe(TELEMETRY_TOPIC, qos=1)
        client.subscribe(STATUS_TOPIC, qos=1)

        print(f"📡 Subscribed: {TELEMETRY_TOPIC}")
        print(f"📡 Subscribed: {STATUS_TOPIC}")

    else:
        print(f"❌ AWS IoT connection failed. Reason code: {reason_code}")


def on_message(client, userdata, message):
    topic = message.topic

    try:
        payload = json.loads(message.payload.decode("utf-8"))
    except json.JSONDecodeError:
        print(f"⚠️ Invalid JSON received on {topic}")
        return

    print("\n" + "=" * 60)
    print(f"📨 MQTT MESSAGE")
    print(f"Topic: {topic}")
    print(json.dumps(payload, indent=4))

    if topic.endswith("/status"):
        print("ℹ️ Device status received.")
        print("=" * 60)
        return

    if not topic.endswith("/telemetry"):
        print("=" * 60)
        return

    try:
        print("🤖 Sending telemetry to Care Agent...")

        result = care_agent(payload)

        urgency_payload = result["urgency"]
        care_payload = result["care"]

        urgency_json = json.dumps(urgency_payload)
        care_json = json.dumps(care_payload)

        client.publish(
            URGENCY_TOPIC,
            urgency_json,
            qos=1
        )

        client.publish(
            CARE_TOPIC,
            care_json,
            qos=1
        )

        print("\n🚨 URGENCY PUBLISHED")
        print(f"Topic: {URGENCY_TOPIC}")
        print(json.dumps(urgency_payload, indent=4))

        print("\n🤖 CARE PUBLISHED")
        print(f"Topic: {CARE_TOPIC}")
        print(json.dumps(care_payload, indent=4))

    except Exception as e:
        print(f"❌ Care Agent processing failed: {e}")

    print("=" * 60)


def create_mqtt_client():

    if not AWS_IOT_ENDPOINT:
        raise RuntimeError("AWS_IOT_ENDPOINT is missing from .env")

    if not os.path.exists(CA_CERT):
        raise FileNotFoundError(
            f"CA certificate not found: {CA_CERT}"
        )

    if not os.path.exists(CLIENT_CERT):
        raise FileNotFoundError(
            f"Client certificate not found: {CLIENT_CERT}"
        )

    if not os.path.exists(PRIVATE_KEY):
        raise FileNotFoundError(
            f"Private key not found: {PRIVATE_KEY}"
        )

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=AWS_IOT_CLIENT_ID
    )

    client.tls_set(
        ca_certs=CA_CERT,
        certfile=CLIENT_CERT,
        keyfile=PRIVATE_KEY,
        tls_version=ssl.PROTOCOL_TLS_CLIENT
    )

    client.on_connect = on_connect
    client.on_message = on_message

    return client


def start_mqtt():

    print("\n🌱 GREENPULSE MQTT BACKEND")
    print("=" * 60)

    print(f"Endpoint: {AWS_IOT_ENDPOINT}")
    print(f"Port: {AWS_IOT_PORT}")
    print(f"Client ID: {AWS_IOT_CLIENT_ID}")

    client = create_mqtt_client()

    print("\n🔐 Connecting using MQTT over TLS...")

    client.connect(
        AWS_IOT_ENDPOINT,
        AWS_IOT_PORT,
        keepalive=60
    )

    print("⏳ Waiting for ESP32 telemetry...\n")

    client.loop_forever()


if __name__ == "__main__":
    start_mqtt()