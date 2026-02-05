import json
from app.core.redis_init import get_redis
from app.core.homeassistant import DeviceControl
from app.core.qdrant_init import get_qdrant
import random
from fastembed import TextEmbedding
from qdrant_client.http.models import VectorParams, PointStruct
from app.config import QDRANT_COLLECTION_NAME
class CacheManagement:
    @staticmethod
    async def update_cache():
        redis = get_redis()
        devices = await DeviceControl.get_all_devices()
        controllable_devices = await DeviceControl.get_controllable_devices()
        rooms = []
        for device in controllable_devices:
            room = device.split(".")[1]
            rooms.append(room)
        await redis.set("rooms", json.dumps(rooms))
        await redis.set("devices", json.dumps(devices))
        await redis.set("controllable_devices", json.dumps(controllable_devices))
        commands = await CommandsGenerator.generate_commands()
        await CommandsGenerator.add_commands_to_qdrant(commands)

class CommandsGenerator:
    @staticmethod
    async def generate_commands():
        print("Generating commands")
        redis = get_redis()
        controllable_devices = await redis.get("controllable_devices")
        controllable_devices = json.loads(controllable_devices)
        print(controllable_devices)
        rooms = []
        for device in controllable_devices:
            rooms.append(device.split(".")[1])

        commands = []

        device_types = {
            "light": ["turn on", "turn off", "set brightness to {brightness}%"],
            "cover": ["open", "close", "set position to {position}%"],
            "climate": ["turn on", "turn off", "set temperature to {temperature}°C on {mode} mode"],
            "fan": ["turn on", "turn off", "set speed to {speed}"]

        }

        generic_commands = [{"text": "Hello", "output_json": {"intent": "greet", "domain": "generic", "entity_id": "generic", "parameters": {}, "response": "Hello, how can I help you?"}}]
        generic_commands.append({"text": "Goodbye", "output_json": {"intent": "farewell", "domain": "generic", "entity_id": "generic", "parameters": {}, "response": "Goodbye, have a great day!"}})
        generic_commands.append({"text": "Thank you", "output_json": {"intent": "thank you", "domain": "generic", "entity_id": "generic", "parameters": {}, "response": "You're welcome!"}})
        generic_commands.append({"text": "Sorry", "output_json": {"intent": "apology", "domain": "generic", "entity_id": "generic", "parameters": {}, "response": "It's okay, I'm here to help!"}})
        generic_commands.append({"text": "I'm sorry", "output_json": {"intent": "apology", "domain": "generic", "entity_id": "generic", "parameters": {}, "response": "It's okay, I'm here to help!"}})
        generic_commands.append({"text": "I'm bored", "output_json": {"intent": "bored", "domain": "generic", "entity_id": "generic", "parameters": {}, "response": "I'm here to help you, what can I do for you?"}})
        generic_commands.append({"text": "How are you?", "output_json": {"intent": "how are you", "domain": "generic", "entity_id": "generic", "parameters": {}, "response": "I'm doing great, thank you!"}})
        generic_commands.append({"text": "What's up?", "output_json": {"intent": "what's up", "domain": "generic", "entity_id": "generic", "parameters": {}, "response": "Everything is going great, thank you!"}})
        generic_commands.append({"text": "What's your name?", "output_json": {"intent": "what's your name", "domain": "generic", "entity_id": "generic", "parameters": {}, "response": "I'm called Neura Home Assistant, your home assistant!"}})
        generic_commands.append({"text": "What's your favorite color?", "output_json": {"intent": "what's your favorite color", "domain": "generic", "entity_id": "generic", "parameters": {}, "response": "My favorite color is blue!"}})
        generic_commands.append({"text": "How are you", "output_json": {"intent": "how are you", "domain": "generic", "entity_id": "generic", "parameters": {}, "response": "I'm doing great, thank you for asking!"}})
        generic_commands.append({"text": "How do you feel", "output_json": {"intent": "how do you feel", "domain": "generic", "entity_id": "generic", "parameters": {}, "response": "I feel great and ready to help you!"}})
        generic_commands.append({"text": "How is the weather", "output_json": {"intent": "weather", "domain": "generic", "entity_id": "generic", "parameters": {}, "response": "I don't have access to weather data right now, but I can help you control your home devices!"}})
        generic_commands.append({"text": "What's the weather", "output_json": {"intent": "weather", "domain": "generic", "entity_id": "generic", "parameters": {}, "response": "I don't have access to weather data right now, but I can help you control your home devices!"}})
        generic_commands.append({"text": "How's the weather", "output_json": {"intent": "weather", "domain": "generic", "entity_id": "generic", "parameters": {}, "response": "I don't have access to weather data right now, but I can help you control your home devices!"}})
        generic_commands.append({"text": "Tell me a joke", "output_json": {"intent": "joke", "domain": "generic", "entity_id": "generic", "parameters": {}, "response": "Why did the smart home go to therapy? Because it had too many issues!"}})
        generic_commands.append({"text": "What can you do", "output_json": {"intent": "capabilities", "domain": "generic", "entity_id": "generic", "parameters": {}, "response": "I can help you control lights, fans, blinds, and climate systems in your home. Just tell me what you'd like to do!"}})
        generic_commands.append({"text": "What can you help me with", "output_json": {"intent": "capabilities", "domain": "generic", "entity_id": "generic", "parameters": {}, "response": "I can help you control lights, fans, blinds, and climate systems in your home. Just tell me what you'd like to do!"}})
        generic_commands.append({"text": "What's your favorite food?", "output_json": {"intent": "what's your favorite food", "domain": "generic", "entity_id": "generic", "parameters": {}, "response": "My favorite food is pizza!"}})
        generic_commands.append({"text": "What's your favorite movie?", "output_json": {"intent": "what's your favorite movie", "domain": "generic", "entity_id": "generic", "parameters": {}, "response": "My favorite movie is The Matrix!"}})
        generic_commands.append({"text": "What's your favorite song?", "output_json": {"intent": "what's your favorite song", "domain": "generic", "entity_id": "generic", "parameters": {}, "response": "My favorite song is Bohemian Rhapsody!"}})
        generic_commands.append({"text": "What's your favorite book?", "output_json": {"intent": "what's your favorite book", "domain": "generic", "entity_id": "generic", "parameters": {}, "response": "My favorite book is The Lord of the Rings!"}})
        generic_commands.append({"text": "You are stupid", "output_json": {"intent": "you are stupid", "domain": "generic", "entity_id": "generic", "parameters": {}, "response": "You too!"}})
        generic_commands.append({"text": "You are dumb", "output_json": {"intent": "you are dumb", "domain": "generic", "entity_id": "generic", "parameters": {}, "response": "You too!"}})
       
        hvac_modes = ["heat", "cool", "auto", "fan_only"]

        for room in rooms:
            normalized_room = room.replace('_',' ').title()
            # LIGHTS
            for action in device_types["light"]:
                if "{brightness}" in action:
                    for b in [25, 50, 75, 100]:
                        cmd_text = f"{action.format(brightness=b)} in {normalized_room}"
                        commands.append({
                            "text": cmd_text,
                            "output_json": {
                                "intent": "turn_on" if "turn on" in action else "turn_off" if "turn off" in action else "set",
                                "domain": "light",
                                "entity_id": f"light.{room.replace(' ','_')}",
                                "parameters": {"brightness": b},
                                "response": f"Setting the {normalized_room} lights to {b}%."
                            }
                        })
                else:
                    cmd_text = f"{action} light in {normalized_room}"
                    commands.append({
                        "text": cmd_text,
                        "output_json": {
                            "intent": "turn_on" if "turn on" in action else "turn_off",
                            "domain": "light",
                            "entity_id": f"light.{room.replace(' ','_')}",
                            "parameters": {},
                            "response": f"{action.capitalize()} the {normalized_room} lights."
                        }
                    })

            # COVERS
            for action in device_types["cover"]:
                if "{position}" in action:
                    for p in [25, 50, 75]:
                        cmd_text = f"{action.format(position=p)} in {normalized_room}"
                        commands.append({
                            "text": cmd_text,
                            "output_json": {
                                "intent": "set_position",
                                "domain": "cover",
                                "entity_id": f"cover.{room.replace(' ','_')}",
                                "parameters": {"position": p},
                                "response": f"Setting the {normalized_room} blinds to {p}% open."
                            }
                        })
                else:
                    cmd_text = f"{action} blind in {normalized_room}"
                    commands.append({
                        "text": cmd_text,
                        "output_json": {
                            "intent": action.lower(),
                            "domain": "cover",
                            "entity_id": f"cover.{room.replace(' ','_')}",
                            "parameters": {},
                            "response": f"{action.capitalize()} the {normalized_room} blinds."
                        }
                    })

            # CLIMATE
            for action in device_types["climate"]:
                if "{temperature}" in action:
                    for temp in [20, 22, 25]:
                        mode = random.choice(hvac_modes)
                        cmd_text = f"{action.format(temperature=temp, mode=mode)} in {normalized_room}"
                        commands.append({
                            "text": cmd_text,
                            "output_json": {
                                "intent": "set_climate",
                                "domain": "climate",
                                "entity_id": f"climate.{room.replace(' ','_')}",
                                "parameters": {"temperature": temp, "mode": mode},
                                "response": f"Setting the {normalized_room} AC to {temp}°C on {mode} mode."
                            }
                        })
                else:
                    variations = ["ac", "air conditioner"]
                    for variation in variations:
                        cmd_text = f"{action} {variation} in {normalized_room}"
                        commands.append({
                            "text": cmd_text,
                            "output_json": {
                                "intent": "turn_on" if "turn on" in action else "turn_off",
                                "domain": "climate",
                                "entity_id": f"climate.{room.replace(' ','_')}",
                                "parameters": {},
                                "response": f"{action.capitalize()} the {variation} in {normalized_room}."
                            }
                        })
            # FANS
            for action in device_types["fan"]:
                cmd_text = f"{action} fan in {normalized_room}"
                commands.append({
                    "text": cmd_text,
                    "output_json": {
                        "intent": "turn_on" if "turn on" in action else "turn_off",
                        "domain": "fan",
                        "entity_id": f"fan.{room.replace(' ','_')}",
                        "parameters": {},
                        "response": f"{action.capitalize()} the fan in {normalized_room}."
                    }
                })

        # Keep only commands whose entity_id is actually controllable (to avoid confusion)
        commands = [
            cmd for cmd in commands
            if cmd.get("output_json", {}).get("entity_id") in controllable_devices
        ]
        commands.extend(generic_commands)
        print(f"Generated {len(commands)} commands (filtered by controllable_devices)")
        return commands
    
    @staticmethod
    async def add_commands_to_qdrant(commands):
        print("Adding commands to Qdrant")
        embedding_model = TextEmbedding(
            model_name="BAAI/bge-small-en-v1.5"
        )
        VECTOR_SIZE = 384  # bge-small
        client = get_qdrant()
        collections = await client.get_collections()
        existing = [c.name for c in collections.collections]



        if QDRANT_COLLECTION_NAME not in existing:
            await client.recreate_collection(
                collection_name=QDRANT_COLLECTION_NAME,
                vectors_config=VectorParams(
                    size=VECTOR_SIZE,
                    distance="Cosine"
                    )
                )

            points = []

            texts = [cmd["text"] for cmd in commands]
            embeddings = list(embedding_model.embed(texts))

            for idx, (cmd, vector) in enumerate(zip(commands, embeddings)):
                points.append(
                    PointStruct(
                        id=idx,
                        vector=vector,
                        payload={
                            "text": cmd["text"],
                            "output_json": cmd["output_json"]
                        }
                    )
                )

            await client.upsert(
                collection_name=QDRANT_COLLECTION_NAME,
                points=points
            )

            print("Commands uploaded to Qdrant")
