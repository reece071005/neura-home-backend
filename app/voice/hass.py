

import requests

# Replace tihs with your local Home Assistant URL and port
HOME_ASSISTANT_URL = "http://localhost:8123/api"
ACCESS_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJjOTU0NGZmOTVmNTg0NDU4YThhYjRkMzc2NDc4YzRkYSIsImlhdCI6MTc2ODMyMDI5MiwiZXhwIjoyMDgzNjgwMjkyfQ.d6JJi6e4lSOj8dJMIRul3ce32E10t4bzb-VKIZlFRoM"  # see below

HEADERS = {
    "Authorization": f"Bearer {ACCESS_TOKEN}",
    "Content-Type": "application/json",
}

def send_light_command(intent, location):
    entity_id = f"light.{location.replace(' ', '_')}"  # e.g., light.living_room

    if intent == "turn_on_light":
        response = requests.post(
            f"{HOME_ASSISTANT_URL}/services/light/turn_on",
            headers=HEADERS,
            json={"entity_id": entity_id}
        )
        return response.ok

    elif intent == "turn_off_light":
        response = requests.post(
            f"{HOME_ASSISTANT_URL}/services/light/turn_off",
            headers=HEADERS,
            json={"entity_id": entity_id}
        )
        return response.ok

    return False
