from rapidfuzz import process, fuzz
import re

KNOWN_ROOMS = ['light.pool_lights_fingerbot', 'light.workshop_lights', 'fan.kitchen_extractor_fan', 'fan.master_bathroom_extractor_fan', 'fan.guest_bathroom_extractor_fan', 'cover.study_blind', 'cover.reece_s_window_blind', 'cover.reece_s_door_blind', 'cover.kitchen_blind', 'cover.jake_s_bedroom_right_blind_2', 'cover.jake_s_bedroom_left_blind_2', 'light.toilet_left', 'light.hue_color_lamp_1_8', 'light.hue_color_candle_3', 'light.shower_recess_left', 'light.hue_lightstrip_1_3', 'light.mirror_left_2', 'light.hue_lightstrip_1_2', 'light.ceiling', 'light.hue_color_lamp_1_7', 'light.vanity_recess', 'light.hue_color_candle_1_2', 'light.hue_white_candle_1_2', 'light.toilet_right_3', 'light.hue_color_candle_4', 'light.shower_recess_right', 'light.hue_color_lamp_1_9', 'light.vanity_left_2', 'light.hue_color_candle_2_2', 'light.mirror_right_2', 'light.hue_color_candle_2', 'light.shower_2', 'light.hue_color_candle_1', 'light.vanity_right_2', 'light.jakes_room', 'light.reeces_balcony', 'light.staircase', 'light.study_balcony', 'light.kids_bathroom', 'light.reece_room', 'light.study', 'light.hue_ensis_up_1', 'light.hue_resonate_outdoor_wall_1', 'light.hue_play_1', 'light.ceiling_10', 'light.hue_color_lamp_1', 'light.hue_lightguide_bulb_1_3', 'light.hue_white_candle_2', 'light.hue_discover_outdoor_wall_1', 'light.hue_color_candle_3_2', 'light.dimmable_light_2', 'light.hue_tento_color_panel_1', 'light.hue_color_candle_2_3', 'light.hue_lightguide_bulb_1_2', 'light.hue_play_gradient_lightstrip_1', 'light.hue_color_lamp_1_4', 'light.hue_white_candle_2_2', 'light.ceiling_5', 'light.hue_ensis_down_1', 'light.hue_color_candle_4_2', 'light.hue_gradient_lightstrip_1_5', 'light.hue_lightguide_bulb_3', 'light.dimmable_light_1', 'light.hue_discover_outdoor_wall_1_2', 'light.hue_play_2_2', 'light.hue_lightguide_bulb_2', 'light.hue_lightstrip_plus_1_3', 'light.hue_discover_outdoor_wall_1_3', 'light.hue_color_lamp_1_2', 'light.hue_white_candle_2_3', 'light.hue_gradient_lightstrip_1_7', 'light.hue_outdoor_wall_1', 'light.hue_gradient_lightstrip_1', 'light.hue_lightguide_bulb_2_2', 'light.hue_color_candle_1_3', 'light.hue_econic_outdoor_wall_1_2', 'light.hue_play_2', 'light.hue_gradient_lightstrip_1_2', 'light.hue_play_1_4', 'light.hue_econic_outdoor_wall_1', 'light.hue_color_lamp_1_3', 'light.hue_gradient_lightstrip_1_6', 'light.hue_lightguide_bulb_1', 'light.hue_gradient_lightstrip_1_3', 'light.hue_tento_color_panel_2', 'light.hue_resonate_outdoor_wall_2', 'light.hue_white_candle_1', 'light.hue_color_lamp_1_5', 'light.hue_white_candle_3', 'light.hue_color_lamp_1_6', 'light.hue_gradient_lightstrip_1_4', 'light.garage_exterior', 'light.pizza', 'light.dining_room', 'light.front_lights', 'light.living_room', 'light.front_door_new', 'light.front_wall', 'light.backyard', 'light.patio', 'light.laundry_room', 'light.lounge', 'light.utility_area', 'light.utility_hall', 'light.kitchen', 'light.front_of_house', 'light.bar_cabinet', 'light.front_patio', 'light.garage_interior', 'light.garage', 'light.shower', 'light.vanity_left', 'light.vanity_recess_left', 'light.vanity_recess_right', 'light.bath_right', 'light.shower_recess', 'light.mirror_left', 'light.ceiling_2', 'light.toilet_left_3', 'light.mirror_right', 'light.hue_lightstrip_1', 'light.vanity_right', 'light.bath_recess', 'light.ceiling_4', 'light.toilet_right', 'light.bath_left', 'light.master_bedroom', 'light.master_bedroom_cupboard', 'light.master_bathroom', 'light.hue_lightstrip_1_4', 'light.ceiling_9', 'light.mirror', 'light.guest_room_ceiling', 'light.ceiling_strip', 'light.hue_gradient_lightstrip_1_8', 'light.mirror_2', 'light.powder_room', 'light.fidelas_bedroom', 'light.guest_room_cupboard', 'light.fidelas_bathroom', 'light.guest_bathroom', 'light.guest_room', 'light.lounge_led', 'light.dining_room_led', 'light.study_led', 'light.living_room_led', 'cover.garage_door_door', 'fan.reece_bedroom_fan', 'fan.guest_room_fan', 'fan.master_bedroom_fan', 'light.reece_bedroom_fan', 'light.guest_room_fan_light', 'light.master_bedroom_fan_light', 'light.smart_garage_door_2209194507145261070248e1e9a71b24_dnd', 'cover.smart_garage_door_2209194507145261070248e1e9a71b24_garage', 'climate.master_bedroom', 'climate.kids_rooms', 'climate.lounge', 'climate.living_room', 'climate.guest_room', 'light.front_door_light', 'light.garden_light', 'light.bar_light', 'light.garage_light', 'fan.kids_bathroom_extractor_fan', 'light.braii']

ROOM_SYNONYMS = {
    "room": "bedroom",
    "bed": "bedroom",
    "bed rm": "bedroom"
}

def normalize(text):
    text = text.lower().replace("_", " ").strip()

    # normalize room synonyms
    for k, v in ROOM_SYNONYMS.items():
        text = re.sub(rf"\b{k}\b", v, text)

    return text

def extract_room(user_text):
    user_text_norm = normalize(user_text)

    # focus only on text after "in"
    match = re.search(r"in (.+)", user_text_norm)
    room_text = match.group(1) if match else user_text_norm

    room_map = {normalize(r): r for r in KNOWN_ROOMS}

    best_match, score, _ = process.extractOne(
        room_text,
        room_map.keys(),
        scorer=fuzz.token_sort_ratio
    )

    if score >= 80:
        return room_map[best_match]

    return None


# ---- TESTS ----
tests = [
    "turn off the lights in reece bedroom",
    "turn off the lights in recee bedroom",
    "turn off lights in reece_room",
    "please switch off the lights in reece room now",
]

for t in tests:
    print(f"Input: {t} --> Matched Room: {extract_room(t)}")
