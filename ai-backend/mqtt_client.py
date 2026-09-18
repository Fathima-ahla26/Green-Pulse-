import json
import os
import ssl

import paho.mqtt.client as mqtt
from dotenv import load_dotenv

from logging_config import logger
from care_agent import care_agent
from weather_agent import get_weather_summary


load_dotenv()


# =========================================================
# AWS IOT CONFIGURATION
# =========================================================

AWS_IOT_ENDPOINT = os.getenv("AWS_IOT_ENDPOINT")

AWS_IOT_PORT = int(
    os.getenv("AWS_IOT_PORT", "8883")
)

AWS_IOT_CLIENT_ID = os.getenv(
    "AWS_IOT_CLIENT_ID",
    "greenpulse-backend"
)


# =========================================================
# TLS CERTIFICATES
# =========================================================

CA_CERT = os.getenv("AWS_IOT_CA_CERT")
CLIENT_CERT = os.getenv("AWS_IOT_CLIENT_CERT")
PRIVATE_KEY = os.getenv("AWS_IOT_PRIVATE_KEY")


# =========================================================
# MQTT TOPICS
# =========================================================

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


# =========================================================
# MQTT CONNECT CALLBACK
# =========================================================

def on_connect(client, userdata, flags, reason_code, properties):

    if reason_code == 0:

        logger.info(
            "Connected to AWS IoT Core"
        )

        telemetry_result = client.subscribe(
            TELEMETRY_TOPIC,
            qos=1
        )

        status_result = client.subscribe(
            STATUS_TOPIC,
            qos=1
        )

        if telemetry_result[0] == mqtt.MQTT_ERR_SUCCESS:

            logger.info(
                "Subscribed to telemetry topic | topic=%s qos=1",
                TELEMETRY_TOPIC
            )

        else:

            logger.error(
                "Failed to subscribe to telemetry topic | topic=%s rc=%s",
                TELEMETRY_TOPIC,
                telemetry_result[0]
            )

        if status_result[0] == mqtt.MQTT_ERR_SUCCESS:

            logger.info(
                "Subscribed to status topic | topic=%s qos=1",
                STATUS_TOPIC
            )

        else:

            logger.error(
                "Failed to subscribe to status topic | topic=%s rc=%s",
                STATUS_TOPIC,
                status_result[0]
            )

    else:

        logger.error(
            "AWS IoT connection failed | reason_code=%s",
            reason_code
        )


# =========================================================
# MQTT MESSAGE CALLBACK
# =========================================================

def on_message(client, userdata, message):

    topic = message.topic

    logger.info(
        "MQTT message received | topic=%s",
        topic
    )

    # -----------------------------------------------------
    # PARSE JSON
    # -----------------------------------------------------

    try:

        payload = json.loads(
            message.payload.decode("utf-8")
        )

    except json.JSONDecodeError:

        logger.error(
            "Invalid JSON received | topic=%s",
            topic
        )

        return

    # -----------------------------------------------------
    # DEVICE STATUS
    # -----------------------------------------------------

    if topic.endswith("/status"):

        logger.info(
            "Device status received | device=%s state=%s ts=%s",
            payload.get("device_id"),
            payload.get("state"),
            payload.get("ts")
        )

        return

    # -----------------------------------------------------
    # ONLY PROCESS TELEMETRY
    # -----------------------------------------------------

    if not topic.endswith("/telemetry"):

        logger.info(
            "MQTT message ignored | topic=%s",
            topic
        )

        return

    # -----------------------------------------------------
    # TELEMETRY LOGGING
    # -----------------------------------------------------

    logger.info(
        "Telemetry received | device=%s seq=%s ts=%s",
        payload.get("device_id"),
        payload.get("seq"),
        payload.get("ts")
    )

    try:

        # =================================================
        # WEATHER AGENT
        # =================================================

        logger.info(
            "Weather agent started | device=%s seq=%s",
            payload.get("device_id"),
            payload.get("seq")
        )

        weather_data = get_weather_summary()

        logger.info(
            "Weather agent completed | location=%s rain_expected=%s",
            weather_data.get("location"),
            weather_data.get("rain_expected")
        )

        # =================================================
        # CARE + DECISION AGENTS
        # =================================================

        logger.info(
            "Care agent started | device=%s seq=%s",
            payload.get("device_id"),
            payload.get("seq")
        )

        result = care_agent(
            payload,
            weather_data
        )

        logger.info(
            "Care agent completed | device=%s seq=%s",
            payload.get("device_id"),
            payload.get("seq")
        )

        # -------------------------------------------------
        # EXTRACT RESULTS
        # -------------------------------------------------

        urgency_payload = result["urgency"]

        care_payload = result["care"]

        decision = result["decision"]

        # =================================================
        # DECISION LOGGING
        # =================================================

        logger.info(
            "Decision completed | device=%s level=%s score=%s eta_hours=%s",
            payload.get("device_id"),
            decision.get("level"),
            decision.get("score"),
            decision.get("next_water_eta_hours")
        )

        # =================================================
        # PUBLISH URGENCY
        # =================================================

        urgency_json = json.dumps(
            urgency_payload
        )

        logger.info(
            "Publishing urgency | topic=%s device=%s",
            URGENCY_TOPIC,
            payload.get("device_id")
        )

        urgency_result = client.publish(
            URGENCY_TOPIC,
            urgency_json,
            qos=1
        )

        if urgency_result.rc == mqtt.MQTT_ERR_SUCCESS:

            logger.info(
                "Urgency published successfully | topic=%s device=%s level=%s",
                URGENCY_TOPIC,
                payload.get("device_id"),
                urgency_payload.get("level")
            )

        else:

            logger.error(
                "Failed to publish urgency | topic=%s rc=%s",
                URGENCY_TOPIC,
                urgency_result.rc
            )

        # =================================================
        # PUBLISH CARE
        # =================================================

        care_json = json.dumps(
            care_payload
        )

        logger.info(
            "Publishing care response | topic=%s device=%s",
            CARE_TOPIC,
            payload.get("device_id")
        )

        care_result = client.publish(
            CARE_TOPIC,
            care_json,
            qos=1
        )

        if care_result.rc == mqtt.MQTT_ERR_SUCCESS:

            logger.info(
                "Care response published successfully | topic=%s device=%s",
                CARE_TOPIC,
                payload.get("device_id")
            )

        else:

            logger.error(
                "Failed to publish care response | topic=%s rc=%s",
                CARE_TOPIC,
                care_result.rc
            )

    except Exception:

        logger.exception(
            "AI backend processing failed | device=%s seq=%s",
            payload.get("device_id"),
            payload.get("seq")
        )

    logger.info(
        "Telemetry processing completed | device=%s seq=%s",
        payload.get("device_id"),
        payload.get("seq")
    )


# =========================================================
# CREATE MQTT CLIENT
# =========================================================

def create_mqtt_client():

    # -----------------------------------------------------
    # CHECK AWS ENDPOINT
    # -----------------------------------------------------

    if not AWS_IOT_ENDPOINT:

        raise RuntimeError(
            "AWS_IOT_ENDPOINT is missing from .env"
        )

    # -----------------------------------------------------
    # CHECK CA CERTIFICATE
    # -----------------------------------------------------

    if not CA_CERT or not os.path.exists(CA_CERT):

        raise FileNotFoundError(
            f"CA certificate not found: {CA_CERT}"
        )

    # -----------------------------------------------------
    # CHECK CLIENT CERTIFICATE
    # -----------------------------------------------------

    if not CLIENT_CERT or not os.path.exists(CLIENT_CERT):

        raise FileNotFoundError(
            f"Client certificate not found: {CLIENT_CERT}"
        )

    # -----------------------------------------------------
    # CHECK PRIVATE KEY
    # -----------------------------------------------------

    if not PRIVATE_KEY or not os.path.exists(PRIVATE_KEY):

        raise FileNotFoundError(
            f"Private key not found: {PRIVATE_KEY}"
        )

    # -----------------------------------------------------
    # CREATE MQTT CLIENT
    # -----------------------------------------------------

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=AWS_IOT_CLIENT_ID
    )

    # =====================================================
    # MQTT OVER TLS
    # =====================================================

    client.tls_set(
        ca_certs=CA_CERT,
        certfile=CLIENT_CERT,
        keyfile=PRIVATE_KEY,
        tls_version=ssl.PROTOCOL_TLS_CLIENT
    )

    logger.info(
        "MQTT TLS configuration initialized"
    )

    # -----------------------------------------------------
    # CALLBACKS
    # -----------------------------------------------------

    client.on_connect = on_connect
    client.on_message = on_message

    return client


# =========================================================
# START MQTT BACKEND
# =========================================================

def start_mqtt():

    logger.info(
        "GREENPULSE MQTT AI BACKEND STARTING"
    )

    logger.info(
        "AWS IoT endpoint=%s",
        AWS_IOT_ENDPOINT
    )

    logger.info(
        "AWS IoT port=%s",
        AWS_IOT_PORT
    )

    logger.info(
        "MQTT client ID=%s",
        AWS_IOT_CLIENT_ID
    )

    logger.info(
        "MQTT over TLS enabled"
    )

    # -----------------------------------------------------
    # CREATE CLIENT
    # -----------------------------------------------------

    client = create_mqtt_client()

    # -----------------------------------------------------
    # CONNECT
    # -----------------------------------------------------

    logger.info(
        "Connecting to AWS IoT Core..."
    )

    try:

        client.connect(
            AWS_IOT_ENDPOINT,
            AWS_IOT_PORT,
            keepalive=60
        )

    except Exception:

        logger.exception(
            "Failed to connect to AWS IoT Core"
        )

        raise

    logger.info(
        "Waiting for telemetry..."
    )

    logger.info(
        "MQTT backend is running"
    )

    # -----------------------------------------------------
    # KEEP MQTT CONNECTION ALIVE
    # -----------------------------------------------------

    try:

        client.loop_forever()

    except KeyboardInterrupt:

        logger.info(
            "GreenPulse MQTT backend stopped by user"
        )

        client.disconnect()

    except Exception:

        logger.exception(
            "MQTT loop stopped unexpectedly"
        )

        client.disconnect()

        raise


# =========================================================
# APPLICATION ENTRY POINT
# =========================================================

if __name__ == "__main__":

    start_mqtt()