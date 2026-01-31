# app/voice/handler.py

import re
import requests

LLM_ENDPOINT = "http://localhost:8080/completion"

class IntentParser:
    def __init__(self, text: str):
        self.text = text.lower().strip()

    def parse(self) -> dict:
        # Rule-based parsing
        if "turn on" in self.text or "switch on" in self.text:
            location = self.extract_location()
            return {
                "intent": "turn_on_light",
                "device": "light",
                "location": location,
                "brightness": None,
                "response": f"Turning on the {location} light."
            }

        if "turn off" in self.text or "switch off" in self.text:
            location = self.extract_location()
            return {
                "intent": "turn_off_light",
                "device": "light",
                "location": location,
                "brightness": None,
                "response": f"Turning off the {location} light."
            }

        if "dim" in self.text or "brightness" in self.text:
            location = self.extract_location()
            brightness = self.extract_brightness()
            return {
                "intent": "set_brightness",
                "device": "light",
                "location": location,
                "brightness": brightness,
                "response": f"Setting brightness of {location} light to {brightness}%."
            }

        # Fallback to LLM
        return self.call_llm()

    def extract_location(self) -> str:
        # This is a placeholder, cann be edited/enhanced later
        known_locations = ["kitchen", "bedroom", "living room", "guest room", "hallway"]
        for loc in known_locations:
            if loc in self.text:
                return loc
        return "current"  # fallback location

    def extract_brightness(self) -> int:
        match = re.search(r"\b(\d{1,3})\s*(percent|%)", self.text)
        if match:
            value = int(match.group(1))
            return min(max(value, 0), 100)  # clamp between 0-100
        if "dim" in self.text:
            return 40  # default dim value
        return 100  # fallback full brightness

    def call_llm(self) -> dict:
        try:
            payload = {
                "prompt": self.text,
                "n_predict": 128
            }
            response = requests.post(LLM_ENDPOINT, json=payload)
            if response.status_code == 200:
                result = response.json()
                content = result.get("content", "{}")

                # parsing the response as json
                import json
                parsed = json.loads(content)
                return parsed

            return {
                "intent": "unknown",
                "device": None,
                "location": None,
                "brightness": None,
                "response": "Sorry, I couldn't understand the command."
            }
        except Exception as e:
            return {
                "intent": "unknown",
                "device": None,
                "location": None,
                "brightness": None,
                "response": f"LLM error: {str(e)}"
            }
