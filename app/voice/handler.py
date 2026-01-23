

def parse_intent(text: str) -> dict:
    """
    Parse the recognized speech text and return an intent dictionary.

    Example return values:
    {
        "intent": "turn_on_light",
        "location": "guest_room_spot_1"
    }
    """

    text = text.lower()

    # turning rhe light's on
    if "turn on" in text and "light" in text:

        if "guest room" in text:
            return {
                "intent": "turn_on_light",
                "location": "guest_room_spot_1"
            }

        elif "living room" in text:
            return {
                "intent": "turn_on_light",
                "location": "living_room"
            }

        elif "bedroom" in text:
            return {
                "intent": "turn_on_light",
                "location": "bedroom"
            }

        else:
            return {
                "intent": "turn_on_light",
                "location": "unknown"
            }

    # turning the lights off
    elif "turn off" in text and "light" in text:

        if "guest room" in text:
            return {
                "intent": "turn_off_light",
                "location": "guest_room_spot_1"
            }

        elif "living room" in text:
            return {
                "intent": "turn_off_light",
                "location": "living_room"
            }

        elif "bedroom" in text:
            return {
                "intent": "turn_off_light",
                "location": "bedroom"
            }

        else:
            return {
                "intent": "turn_off_light",
                "location": "unknown"
            }

    # for future
    elif "temperature" in text:
        return {
            "intent": "get_temperature"
        }

    # if the command is unknown
    return {
        "intent": "unknown"
    }
