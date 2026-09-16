def resolve_decision(sensor_data, weather_data):
    """
    Combines environment and weather information
    to determine the final watering urgency.

    This is the decision/resolution layer of GreenPulse.
    """

    # ---------------------------------------------------------
    # GET SOIL MOISTURE
    # ---------------------------------------------------------

    if "readings" in sensor_data:
        soil_moisture = sensor_data["readings"].get(
            "soil_moisture_pct"
        )
    else:
        soil_moisture = sensor_data.get(
            "soil_moisture"
        )

    # ---------------------------------------------------------
    # GET WEATHER INFORMATION
    # ---------------------------------------------------------

    rain_expected = weather_data.get(
        "rain_expected",
        False
    )

    rain_probability = weather_data.get(
        "max_rain_probability_pct",
        0
    )

    next_12h_rain = weather_data.get(
        "next_12h_rain_mm",
        0
    )

    # ---------------------------------------------------------
    # ENVIRONMENT DECISION
    # ---------------------------------------------------------

    if soil_moisture is None:

        environment_level = "amber"
        environment_score = 0.5

    elif soil_moisture < 20:

        environment_level = "red"
        environment_score = 0.90

    elif soil_moisture < 35:

        environment_level = "amber"
        environment_score = 0.62

    else:

        environment_level = "green"
        environment_score = 0.20

    # ---------------------------------------------------------
    # WEATHER CONFLICT RESOLUTION
    # ---------------------------------------------------------

    significant_rain_expected = (
        rain_expected
        and (
            rain_probability >= 50
            or next_12h_rain >= 1.0
        )
    )

    # Very dry soil + significant rain expected
    if (
        environment_level == "red"
        and significant_rain_expected
    ):

        final_level = "amber"
        final_score = 0.65
        next_water_eta = 6.0

        reason = (
            "Soil moisture is very low, but significant "
            "rain is expected soon. Recheck the soil "
            "after rainfall before watering heavily."
        )

    # Moderately dry soil + rain expected
    elif (
        environment_level == "amber"
        and significant_rain_expected
    ):

        final_level = "green"
        final_score = 0.30
        next_water_eta = None

        reason = (
            "Soil moisture is moderately low, but expected "
            "rain may provide sufficient moisture."
        )

    # No rain conflict
    else:

        final_level = environment_level
        final_score = environment_score

        if environment_level == "red":
            next_water_eta = 2.0

            reason = (
                "Soil moisture is very low and significant "
                "rain is not expected soon."
            )

        elif environment_level == "amber":
            next_water_eta = 12.0

            reason = (
                "Soil moisture is moderately low."
            )

        else:
            next_water_eta = None

            reason = (
                "Soil moisture is currently at a healthy level."
            )

    return {
        "level": final_level,
        "score": final_score,
        "next_water_eta_hours": next_water_eta,
        "reason": reason,
        "environment_level": environment_level,
        "rain_expected": rain_expected,
        "rain_probability_pct": rain_probability,
        "next_12h_rain_mm": next_12h_rain
    }