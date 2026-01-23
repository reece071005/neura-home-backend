from app.voice.recognizer import recognize_command_from_mic
from app.voice.handler import parse_intent
from app.voice.hass import send_light_command

if __name__ == "__main__":
    text = recognize_command_from_mic()
    print("Recognized:", text)

    intent_data = parse_intent(text)
    print("Parsed Intent:", intent_data)

    success = send_light_command(intent_data["intent"], intent_data.get("location", ""))
    print("Device Command Success:", success)
