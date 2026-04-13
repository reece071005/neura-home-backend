#!/usr/bin/env python3
import asyncio
import json
import os

import websockets  # pip install websockets

HOME_ASSISTANT_URL = "wss://70i5piqxrwxbmwtnseu92fpobavxtcpe.ui.nabu.casa/api/websocket"
ACCESS_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJjOTU0NGZmOTVmNTg0NDU4YThhYjRkMzc2NDc4YzRkYSIsImlhdCI6MTc2ODMyMDI5MiwiZXhwIjoyMDgzNjgwMjkyfQ.d6JJi6e4lSOj8dJMIRul3ce32E10t4bzb-VKIZlFRoM"




async def listen_events(url: str, token: str, event_type: str | None):
    async with websockets.connect(url) as ws:
        msg = await ws.recv()
        print("<<", msg)

        await ws.send(json.dumps({
            "type": "auth",
            "access_token": token,
        }))
        auth_reply = await ws.recv()
        print("<<", auth_reply)

        #  Sub to ebents
        subscription_id = 1
        subscribe_msg = {
            "id": subscription_id,
            "type": "subscribe_events",
        }
        if event_type:
            subscribe_msg["event_type"] = event_type

        await ws.send(json.dumps(subscribe_msg))
        sub_reply = await ws.recv()
        print("<<", sub_reply)

        # print all events
        print("Listening for events... Press Ctrl+C to stop.\n")
        try:
            while True:
                raw = await ws.recv()
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    print("<< (non‑JSON)", raw)
                    continue

                # Filter out memory/cpu utilization entities
                if isinstance(data, dict) and data.get("type") == "event":
                    event = data.get("event", {}) or {}
                    event_data = event.get("data", {}) or {}
                    entity_id = event_data.get("entity_id")

                    # Some events nest entity_id under new_state/old_state
                    if not entity_id:
                        new_state = event_data.get("new_state") or {}
                        if isinstance(new_state, dict):
                            entity_id = new_state.get("entity_id")

                    if isinstance(entity_id, str):
                        if not (
                            "binary_sensor" in entity_id
                        ):
                            # Skipping these noisy metrics
                            continue

                print("<< event:")
                print(json.dumps(data, indent=2))
        except KeyboardInterrupt:
            print("Exiting, unsubscribing from events...")
        except websockets.ConnectionClosed as e:
            print(f"Connection closed: {e}")
        finally:
            try:
                unsubscribe_msg = {
                    "id": subscription_id + 1,
                    "type": "unsubscribe_events",
                    "subscription": subscription_id,
                }
                await ws.send(json.dumps(unsubscribe_msg))
                reply = await ws.recv()
                print("<< unsubscribe reply:")
                print(reply)
            except websockets.ConnectionClosed:
                # Connection already closed; nothing to do
                pass


def _build_ws_url(base_url: str) -> str:
    if base_url.startswith("http"):
        ws_url = base_url.replace("http", "ws", 1)
    else:
        ws_url = base_url

    #  ends with /api/websocket
    if ws_url.endswith("/websocket"):
        return ws_url
    if ws_url.endswith("/api"):
        return ws_url + "/websocket"
    return ws_url.rstrip("/") + "/api/websocket"


def main():
    # safety
    token = os.getenv("HASS_TOKEN", ACCESS_TOKEN)
    ws_url = _build_ws_url(HOME_ASSISTANT_URL)
    asyncio.run(listen_events(ws_url, token, None))


if __name__ == "__main__":
    main()