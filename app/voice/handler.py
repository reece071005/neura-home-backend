# app/voice/handler.py

import re

class IntentParser:
    def __init__(self, text: str):
        self.text = text.lower()

    def parse(self) -> dict:
        intent = "unknown"
        location = "unknown"
        brightness = None

        # Identify location
        if "guest room" in self.text:
            location = "guest_room_spot_1"
        elif "living room" in self.text:
            location = "living_room"
        elif "bedroom" in self.text:
            location = "bedroom"

        # Brightness (e.g., "set light to 80%" or "dim light to 40")
        brightness_match = re.search(r"(\d{1,3})\s*%", self.text)
        if brightness_match:
            brightness_value = int(brightness_match.group(1))
            brightness = min(max(int(brightness_value * 2.55), 0), 255)  # convert 0-100% to 0-255 scale

        # Intent detection
        if "turn on" in self.text and "light" in self.text:
            intent = "turn_on_light"
        elif "turn off" in self.text and "light" in self.text:
            intent = "turn_off_light"
        elif "dim" in self.text or "brightness" in self.text or "set to" in self.text:
            intent = "turn_on_light"  # We'll use brightness + on for simplicity

        return {
            "intent": intent,
            "location": location,
            "brightness": brightness
        }
