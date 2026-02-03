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

        hvac_modes = ["heat", "cool", "auto", "fan_only"]

        for room in rooms:
            # LIGHTS
            for action in device_types["light"]:
                if "{brightness}" in action:
                    for b in [25, 50, 75, 100]:
                        cmd_text = f"{action.format(brightness=b)} in {room}"
                        commands.append({
                            "text": cmd_text,
                            "output_json": {
                                "intent": "turn_on" if "turn on" in action else "turn_off" if "turn off" in action else "set",
                                "domain": "light",
                                "entity_id": f"light.{room.replace(' ','_')}",
                                "parameters": {"brightness": b},
                                "response": f"Setting the {room} lights to {b}%."
                            }
                        })
                else:
                    cmd_text = f"{action} light in {room}"
                    commands.append({
                        "text": cmd_text,
                        "output_json": {
                            "intent": "turn_on" if "turn on" in action else "turn_off",
                            "domain": "light",
                            "entity_id": f"light.{room.replace(' ','_')}",
                            "parameters": {},
                            "response": f"{action.capitalize()} the {room} lights."
                        }
                    })

            # COVERS
            for action in device_types["cover"]:
                if "{position}" in action:
                    for p in [25, 50, 75]:
                        cmd_text = f"{action.format(position=p)} in {room}"
                        commands.append({
                            "text": cmd_text,
                            "output_json": {
                                "intent": "set_position",
                                "domain": "cover",
                                "entity_id": f"cover.{room.replace(' ','_')}_blind",
                                "parameters": {"position": p},
                                "response": f"Setting the {room} blinds to {p}% open."
                            }
                        })
                else:
                    cmd_text = f"{action} blind in {room}"
                    commands.append({
                        "text": cmd_text,
                        "output_json": {
                            "intent": action.lower(),
                            "domain": "cover",
                            "entity_id": f"cover.{room.replace(' ','_')}_blind",
                            "parameters": {},
                            "response": f"{action.capitalize()} the {room} blinds."
                        }
                    })

            # CLIMATE
            for action in device_types["climate"]:
                if "{temperature}" in action:
                    for temp in [20, 22, 25]:
                        mode = random.choice(hvac_modes)
                        cmd_text = f"{action.format(temperature=temp, mode=mode)} in {room}"
                        commands.append({
                            "text": cmd_text,
                            "output_json": {
                                "intent": "set_climate",
                                "domain": "climate",
                                "entity_id": f"climate.{room.replace(' ','_')}",
                                "parameters": {"temperature": temp, "mode": mode},
                                "response": f"Setting the {room} AC to {temp}°C on {mode} mode."
                            }
                        })
                else:
                    variations = ["ac", "air conditioner"]
                    for variation in variations:
                        cmd_text = f"{action} {variation} in {room}"
                        commands.append({
                            "text": cmd_text,
                            "output_json": {
                                "intent": "turn_on" if "turn on" in action else "turn_off",
                                "domain": "climate",
                                "entity_id": f"climate.{room.replace(' ','_')}",
                                "parameters": {},
                                "response": f"{action.capitalize()} the {variation} in {room}."
                            }
                        })
            # FANS
            for action in device_types["fan"]:
                cmd_text = f"{action} fan in {room}"
                commands.append({
                    "text": cmd_text,
                    "output_json": {
                        "intent": "turn_on" if "turn on" in action else "turn_off",
                        "domain": "fan",
                        "entity_id": f"fan.{room.replace(' ','_')}",
                        "parameters": {},
                        "response": f"{action.capitalize()} the fan in {room}."
                    }
                })

        print(f"Generated {len(commands)} commands")
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
