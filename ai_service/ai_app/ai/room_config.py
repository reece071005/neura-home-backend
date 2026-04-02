##this file is no longer in use and it here for falling back purposes omnly.

ROOM_CONFIG = {
    "reece_room": {
        "lights": ["reece_room"],
        "climate": ["kids_rooms"],
        "covers": ["reece_s_window_blind", "reece_s_door_blind"],
        "motion": ["kids_rooms_occupancy"],

        # NEW: preconditioning plan (arrival-based climate)
        "precondition": {
            "enabled": True,
            "arrival_time_weekday": "18:30",   # Dubai local time
            "arrival_time_weekend": "13:00",
            "lead_minutes": 20,                # start AC this many minutes before arrival
            "min_temp_delta": 1.0,             # only act if |setpoint - current| >= this
            "fallback_setpoint": 24.0,         # used if model is missing/unavailable
        },
    },
    "guest_room": {
        "lights": ["guest_room"],
        "climate": ["guest_room"],
        "covers": [],
        "motion": ["guest_room_occupancy"],

        "precondition": {
            "enabled": False,                  # set True if you want guest room preconditioning too
            "arrival_time_weekday": "18:30",
            "arrival_time_weekend": "13:00",
            "lead_minutes": 20,
            "min_temp_delta": 1.0,
            "fallback_setpoint": 24.0,
        },
    },
}

