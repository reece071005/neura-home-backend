import re
import spacy
from spacy.matcher import PhraseMatcher, Matcher

# Load English model once
nlp = spacy.load("en_core_web_sm")

# ---------- Define Rooms & Devices (with synonyms) ----------

# Canonical room names -> list of synonyms/phrases
ROOM_SYNONYMS = {
    "bedroom": [
        "bedroom",
    ],
    # Treat "Reece" as an occupant hint (via OCCUPANT_WORDS), not as its own room.
    # This prevents phrases like "Reece bath" from being normalized to "Reece bedroom".
    "reece bedroom": [
        "reece bedroom",
    ],
    "living room": [
        "living room",
        # add more like "lounge", "family room" here
    ],
    "kitchen": [
        "kitchen",
    ],
    "bathroom": [
        "bathroom",
    ],
}

# Canonical device names -> list of synonyms/phrases
DEVICE_SYNONYMS = {
    "light": [
        "light",
        "lights",
        "lightbulb",
        "bulb",
        "lamp",
        "brightness",
    ],
    "fan": [
        "fan",
        "fans",
    ],
    "climate": [
        "ac",
        "air conditioner",
        "climate",
    ],
    "cover": [
        "blinds",
        "curtains",
        "cover",
        "window blind",
        "blind"
    ],
}

# Intent phrases -> canonical intent label
# Order matters: longer/more specific phrases should appear first.
INTENT_PHRASES: list[tuple[str, str]] = [
    ("turn on", "turn_on"),
    ("switch on", "turn_on"),
    ("put on", "turn_on"),
    ("turn off", "turn_off"),
    ("switch off", "turn_off"),
    ("shut off", "turn_off"),
    ("set brightness", "set_brightness"),
    ("set temperature", "set_temperature"),
    ("set", "set"),
    ("open", "open"),
    ("close", "close"),
]

# Common little words we don't want to use for location matching
STOPWORDS = {
    "in",
    "at",
    "on",
    "the",
    "a",
    "an",
    "to",
    "of",
    "please",
    # Action verbs (even if intent detection misses them)
    "turn",
    "switch",
    "put",
    "shut",
    "open",
    "close",
    "off",
    "set",
}


# ---------- Dynamic location synonyms from entity ids ----------

ENTITY_IDS = [
    "light.pool_lights_fingerbot",
    "light.workshop_lights",
    "fan.kitchen_extractor_fan",
    "fan.master_bathroom_extractor_fan",
    "fan.guest_bathroom_extractor_fan",
    "fan.kids_bathroom_extractor_fan",
    "cover.study_blind",
    "cover.reece_s_window_blind",
    "cover.reece_s_door_blind",
    "cover.kitchen_blind",
    "cover.jake_s_bedroom_right_blind_2",
    "cover.jake_s_bedroom_left_blind_2",
    "light.hue_lightstrip_1_4",
    "light.ceiling_9",
    "light.mirror",
    "light.guest_room_ceiling",
    "light.ceiling_strip",
    "light.hue_gradient_lightstrip_1_8",
    "light.mirror_2",
    "light.powder_room",
    "light.fidelas_bedroom",
    "light.guest_room_cupboard",
    "light.fidelas_bathroom",
    "light.guest_bathroom",
    "light.guest_room",
    "light.toilet_left",
    "light.hue_color_lamp_1_8",
    "light.hue_color_candle_3",
    "light.shower_recess_left",
    "light.hue_lightstrip_1_3",
    "light.mirror_left_2",
    "light.hue_lightstrip_1_2",
    "light.ceiling",
    "light.hue_color_lamp_1_7",
    "light.vanity_recess",
    "light.hue_color_candle_1_2",
    "light.hue_white_candle_1_2",
    "light.toilet_right_3",
    "light.hue_color_candle_4",
    "light.shower_recess_right",
    "light.hue_color_lamp_1_9",
    "light.vanity_left_2",
    "light.hue_color_candle_2_2",
    "light.mirror_right_2",
    "light.hue_color_candle_2",
    "light.shower_2",
    "light.hue_color_candle_1",
    "light.vanity_right_2",
    "light.jakes_room",
    "light.reeces_balcony",
    "light.staircase",
    "light.study_balcony",
    "light.kids_bathroom",
    "light.reece_room",
    "light.study",
    "light.shower",
    "light.vanity_left",
    "light.vanity_recess_left",
    "light.vanity_recess_right",
    "light.bath_right",
    "light.shower_recess",
    "light.mirror_left",
    "light.ceiling_2",
    "light.toilet_left_3",
    "light.mirror_right",
    "light.hue_lightstrip_1",
    "light.vanity_right",
    "light.bath_recess",
    "light.ceiling_4",
    "light.toilet_right",
    "light.bath_left",
    "light.master_bedroom",
    "light.master_bedroom_cupboard",
    "light.master_bathroom",
    "light.hue_ensis_up_1",
    "light.hue_resonate_outdoor_wall_1",
    "light.hue_play_1",
    "light.ceiling_10",
    "light.hue_color_lamp_1",
    "light.hue_lightguide_bulb_1_3",
    "light.hue_white_candle_2",
    "light.hue_discover_outdoor_wall_1",
    "light.hue_color_candle_3_2",
    "light.dimmable_light_2",
    "light.hue_tento_color_panel_1",
    "light.hue_color_candle_2_3",
    "light.hue_lightguide_bulb_1_2",
    "light.hue_play_gradient_lightstrip_1",
    "light.hue_color_lamp_1_4",
    "light.hue_white_candle_2_2",
    "light.ceiling_5",
    "light.hue_ensis_down_1",
    "light.hue_color_candle_4_2",
    "light.hue_gradient_lightstrip_1_5",
    "light.hue_lightguide_bulb_3",
    "light.dimmable_light_1",
    "light.hue_discover_outdoor_wall_1_2",
    "light.hue_play_2_2",
    "light.hue_lightguide_bulb_2",
    "light.hue_lightstrip_plus_1_3",
    "light.hue_discover_outdoor_wall_1_3",
    "light.hue_color_lamp_1_2",
    "light.hue_white_candle_2_3",
    "light.hue_gradient_lightstrip_1_7",
    "light.hue_outdoor_wall_1",
    "light.hue_gradient_lightstrip_1",
    "light.hue_lightguide_bulb_2_2",
    "light.hue_color_candle_1_3",
    "light.hue_econic_outdoor_wall_1_2",
    "light.hue_play_2",
    "light.hue_gradient_lightstrip_1_2",
    "light.hue_play_1_4",
    "light.hue_econic_outdoor_wall_1",
    "light.hue_color_lamp_1_3",
    "light.hue_gradient_lightstrip_1_6",
    "light.hue_lightguide_bulb_1",
    "light.hue_gradient_lightstrip_1_3",
    "light.hue_tento_color_panel_2",
    "light.hue_resonate_outdoor_wall_2",
    "light.hue_white_candle_1",
    "light.hue_color_lamp_1_5",
    "light.hue_white_candle_3",
    "light.hue_color_lamp_1_6",
    "light.hue_gradient_lightstrip_1_4",
    "light.garage_exterior",
    "light.pizza",
    "light.dining_room",
    "light.front_lights",
    "light.living_room",
    "light.front_door_new",
    "light.front_wall",
    "light.braii",
    "light.backyard",
    "light.patio",
    "light.laundry_room",
    "light.lounge",
    "light.utility_area",
    "light.utility_hall",
    "light.kitchen",
    "light.front_of_house",
    "light.bar_cabinet",
    "light.front_patio",
    "light.garage_interior",
    "light.garage",
    "light.front_door_light",
    "light.garden_light",
    "light.bar_light",
    "light.garage_light",
    "light.lounge_led",
    "light.dining_room_led",
    "light.study_led",
    "light.living_room_led",
    "light.smart_garage_door_2209194507145261070248e1e9a71b24_dnd",
    "cover.smart_garage_door_2209194507145261070248e1e9a71b24_garage",
    "climate.master_bedroom",
    "climate.kids_rooms",
    "climate.lounge",
    "climate.living_room",
    "climate.guest_room",
    "cover.garage_door_door",
    "fan.reece_bedroom_fan",
    "fan.guest_room_fan",
    "fan.master_bedroom_fan",
]


def tokenize_location(entity_id: str, user_has_reece: bool = False) -> list[str]:
    """
    Tokenize the location part of an entity_id.
    If user_has_reece is True, normalize "recess" and "reeces" to "reece"
    for matching purposes.
    """
    if "." not in entity_id:
        raw_tokens = entity_id.replace("_", " ").split()
    else:
        _, location_raw = entity_id.split(".", 1)
        raw_tokens = location_raw.replace("_", " ").split()
    
    if user_has_reece:
        # When user says "reece", treat "recess" and "reeces" as "reece"
        normalized = []
        for tok in raw_tokens:
            tok_lower = tok.lower()
            if tok_lower in {"recess", "reeces"}:
                normalized.append("reece")
            else:
                normalized.append(tok)
        return normalized
    return raw_tokens


# ---------- Token normalization & matching ----------

# Map common mis-hearings / spelling variants to canonical tokens
ALIASES = {
    # Reece
    "reece": "reece",
    "reeces": "reece",
    "reece's": "reece",
    "recess": "reece",
    "reecess": "reece",
    "recees": "reece",
    # Jake
    "jakes": "jake",
    "jake's": "jake",
    # Kids
    "kid": "kids",
    "kid's": "kids",
}

def normalize_token(t: str) -> str:
    t = t.lower()
    t = re.sub(r"[^a-z0-9']+", "", t)  # strip punctuation
    # trivial plural normalization
    if t.endswith("s") and len(t) > 3:
        t = t[:-1]
    # Apply alias mapping (for mis-hearings like "recess" -> "reece")
    return ALIASES.get(t, t)


def detect_device(text: str) -> str | None:
    """
    Detect canonical device from the text using DEVICE_SYNONYMS.
    Returns "light" | "fan" | "climate" | "cover" | None.
    """
    text_lower = text.lower()
    tokens = text_lower.split()
    for tok in tokens:
        for device, syns in DEVICE_SYNONYMS.items():
            if tok in syns:
                return device
    return None


def detect_intent(text: str) -> str | None:
    """
    Detect canonical intent (turn_on, turn_off, open, close, set, etc.).

    Handles phrases like:
    - "turn on", "switch on", "put on", including patterns like
      "turn light on", "switch the ac on"
    - "turn off", "switch off", "shut off"
    - "open", "close"
    - "set brightness", "set temperature", "set ..."
    """
    t = text.lower()
    tokens = t.split()

    # token-based patterns for on/off
    for i, tok in enumerate(tokens):
        if tok in {"turn", "switch", "put"}:
            # look ahead for "on"/"off"
            if any(follow in {"on"} for follow in tokens[i + 1 :]):
                return "turn_on"
            if any(follow in {"off"} for follow in tokens[i + 1 :]):
                return "turn_off"

    # single-word intents
    if "open" in tokens:
        return "open"
    if "close" in tokens or "shut" in tokens:
        return "close"

    # "set brightness", "set temperature", generic "set"
    if "set" in tokens or "put" in tokens:
        if "brightness" in tokens:
            return "set_brightness"
        if "temperature" in tokens or "degrees" in tokens or "degree" in tokens:
            return "set_temperature"
        return "set"

    # Fallback: phrase-based scan for any custom patterns in INTENT_PHRASES
    for phrase, label in INTENT_PHRASES:
        if phrase in t:
            return label

    return None


def extract_location_tokens(text: str, device: str | None, intent: str | None) -> list[str]:
    """
    Strip out intent and device words from the user text and return the
    remaining tokens for location/entity matching.
    """
    text_lower = text.lower()
    tokens = text_lower.split()

    # Words that belong to any intent phrase
    intent_words: set[str] = set()
    for phrase, _ in INTENT_PHRASES:
        if phrase in text_lower:
            intent_words.update(phrase.split())

    # Words that belong to this specific device (if detected)
    device_words: set[str] = set()
    if device:
        for dev, syns in DEVICE_SYNONYMS.items():
            if dev == device:
                device_words.update(syns)
                device_words.add(dev)
                break

    cleaned: list[str] = []
    for tok in tokens:
        base = normalize_token(tok)
        if not base:
            continue
        if base in intent_words:
            continue
        if base in device_words:
            continue
        if base in STOPWORDS:
            continue
        cleaned.append(base)

    return cleaned


def extract_parameters(text: str, device: str | None, intent: str | None) -> dict:
    """
    Extract structured parameters from the user command:
    - For lights: brightness (0-100%)
    - For fans: percentage (0-100%) and mode (low/medium/high)
    - For AC/climate: temperature (degrees) and mode (cool/heat/auto)
    
    Returns a dict with keys like "brightness", "percentage", "temperature", "mode".
    """
    params: dict = {}
    text_lower = text.lower()
    tokens = text_lower.split()
    
    # --- Brightness for lights ---
    if device == "light":
        # Match patterns like "80%", "80 percent", "brightness 80"
        # Note: no trailing \b so that '%' is matched correctly.
        brightness_match = re.search(r"\b(\d{1,3})\s*(percent|%|percents)", text_lower)
        if brightness_match:
            value = int(brightness_match.group(1))
            params["brightness"] = max(0, min(value, 100))
        elif "brightness" in text_lower or "bright" in text_lower:
            # If "dim" mentioned without number, use default dim level
            if "dim" in text_lower:
                params["brightness"] = 40
    
    # --- Fan: percentage and mode ---
    if device == "fan":
        # Percentage: "30%", "50 percent"
        fan_pct_match = re.search(r"\b(\d{1,3})\s*(percent|%|percents)", text_lower)
        if fan_pct_match:
            value = int(fan_pct_match.group(1))
            params["percentage"] = max(0, min(value, 100))
        
        # Mode: low, medium, high
        FAN_MODES = {"low", "medium", "mid", "high", "max", "maximum"}
        for tok in tokens:
            if tok in FAN_MODES:
                if tok in {"max", "maximum"}:
                    params["mode"] = "high"
                elif tok == "mid":
                    params["mode"] = "medium"
                else:
                    params["mode"] = tok
                break

    # --- Cover: position percentage ---
    if device == "cover":
        # Position: "open to 50%", "set position to 25 percent", "close to 0%"
        pos_match = re.search(r"\b(\d{1,3})\s*(percent|%|percents)", text_lower)
        if pos_match:
            value = int(pos_match.group(1))
            params["position"] = max(0, min(value, 100))
    
    # --- AC/Climate: temperature and mode ---
    if device == "climate":
        # Temperature: "22 degrees", "24c", "set to 25"
        temp_match = re.search(r"\b(\d{1,2})\s*(degrees|degree|deg|c|celsius)\b", text_lower)
        if temp_match:
            params["temperature"] = int(temp_match.group(1))
        else:
            # Fallback: any number when "set temperature" or "set ac" is mentioned
            if "set" in tokens and ("temperature" in tokens or "ac" in tokens):
                num_match = re.search(r"\b(\d{1,2})\b", text_lower)
                if num_match:
                    params["temperature"] = int(num_match.group(1))
        
        # Mode: cool, heat, auto, heating, cooling
        AC_MODES = {"cool", "cooling", "heat", "heating", "auto"}
        for tok in tokens:
            if tok in AC_MODES:
                if tok in {"cooling", "cool"}:
                    params["mode"] = "cool"
                elif tok in {"heating", "heat"}:
                    params["mode"] = "heat"
                else:
                    params["mode"] = tok
                break
    
    return params


def score_match(user_tokens: list[str], loc_tokens: list[str], user_has_reece: bool = False) -> float:
    """
    user_tokens: tokens from user utterance (already split)
    loc_tokens:  tokens from entity location part ("kids_rooms" -> ["kids","rooms"])
    user_has_reece: if True, normalize "recess"/"reeces" in loc_tokens to "reece"
    """
    u = {normalize_token(t) for t in user_tokens if t.strip()}
    # Normalize location tokens, applying reece normalization if needed
    l_tokens_normalized = []
    for t in loc_tokens:
        t_norm = normalize_token(t)
        if user_has_reece and t_norm in {"recess", "reeces"}:
            l_tokens_normalized.append("reece")
        else:
            l_tokens_normalized.append(t_norm)
    l = {t for t in l_tokens_normalized if t.strip()}

    if not u or not l:
        return 0.0

    # Occupant words (reece, kids, jake, etc.)
    OCCUPANT_WORDS = {"reece", "kids", "jake", "jakes", "guest", "master", "fidelas"}
    # Location keywords (bathroom, vanity, room, bedroom, etc.)
    LOCATION_KEYWORDS = {
        "bathroom", "bath", "vanity", "room", "bedroom", "balcony", "study",
        "kitchen", "lounge", "living", "hall", "hallway", "stairs", "staircase",
        "toilet", "powder", "shower",
    }

    # Categorize overlaps
    exact = u & l
    user_occupants = u & OCCUPANT_WORDS
    user_locations = u & LOCATION_KEYWORDS
    loc_occupants = l & OCCUPANT_WORDS
    loc_locations = l & LOCATION_KEYWORDS

    score = 0.0

    # Exact matches: base score
    score += 2.0 * len(exact)
    
    # Special boost: if user's first/primary token exactly matches entity's first token
    # (e.g. "pool" matches "pool_lights_fingerbot")
    if user_tokens and l_tokens_normalized:
        user_first = normalize_token(user_tokens[0])
        loc_first = l_tokens_normalized[0]
        if user_first == loc_first:
            score += 3.0  # Strong boost for primary word match
    
    # Boost when both occupant AND location match (e.g. "reece vanity" matches "vanity_recess")
    if user_occupants & loc_occupants and user_locations & loc_locations:
        score += 3.0  # Strong boost for occupant+location combo
    
    # Location words are very important
    location_overlap = user_locations & loc_locations
    
    # If the only overlap is a generic word like \"room\" and there is no
    # occupant overlap, treat this as \"no meaningful match\".
    if not (user_occupants & loc_occupants) and location_overlap and location_overlap <= {"room"}:
        return 0.0
    
    score += 2.0 * len(location_overlap)
    
    # Occupant words are helpful
    occupant_overlap = user_occupants & loc_occupants
    score += 1.5 * len(occupant_overlap)

    # If the user explicitly mentioned an occupant (e.g. "reece") and the candidate
    # entity also contains an occupant word, but they don't match, penalize hard.
    # This prevents "reece bedroom" picking a "jake bedroom" entity just because
    # it shares "bedroom".
    if user_occupants and loc_occupants and not occupant_overlap:
        score -= 3.0

    # Special handling: if user explicitly mentions bathroom/bath/vanity,
    # strongly prefer entities with those words and penalize others
    BATHROOM_WORDS = {"bathroom", "bath"}
    VANITY_WORDS = {"vanity"}
    ROOM_WORDS = {"room", "bedroom"}

    user_has_bathroom = bool(u & BATHROOM_WORDS)
    user_has_vanity = bool(u & VANITY_WORDS)
    user_has_room = bool(u & ROOM_WORDS) and not (user_has_bathroom or user_has_vanity)

    loc_has_bathroom = bool(l & BATHROOM_WORDS)
    loc_has_vanity = bool(l & VANITY_WORDS)
    loc_has_room = bool(l & ROOM_WORDS)

    if user_has_bathroom:
        if loc_has_bathroom:
            score += 4.0  # Strong boost for bathroom match
        elif not loc_has_bathroom:
            score -= 3.0  # Strong penalty if user said bathroom but entity doesn't have it

    if user_has_vanity:
        if loc_has_vanity:
            score += 4.0  # Strong boost for vanity match
        elif not loc_has_vanity:
            score -= 3.0  # Strong penalty if user said vanity but entity doesn't have it

    if user_has_room:
        # User said "room"/"bedroom" but NOT bathroom/vanity
        if loc_has_bathroom or loc_has_vanity:
            score -= 2.0  # Penalize bathroom/vanity entities when user wants room
        elif loc_has_room:
            score += 1.5  # Boost room entities

    # Partial overlaps (e.g. "bath" vs "bathroom")
    for ut in u - exact:
        for lt in l - exact:
            # Require reasonably long tokens to avoid spurious matches like
            # \"max\" → \"master\" or \"to\" → \"toilet\".
            if (
                ut
                and lt
                and len(ut) >= 4
                and len(lt) >= 4
                and ut not in ROOM_WORDS
                and lt not in ROOM_WORDS
                and (ut in lt or lt in ut)
            ):
                score += 1.0
                break

    # Normalize by location length (but don't penalize too harshly)
    return score / max(len(l), 1)

MIN_SCORE = 0.8  # Lowered to handle cases like "reece vanity" matching vanity_recess entities 
def best_entity_for_text(text: str, entity_ids: list[str]) -> str | None:
    """
    Return the single best-matching entity id for the given user text,
    or None if the best score is below MIN_SCORE.

    This function:
    - Detects device & intent
    - Builds location-only tokens (text minus intent/device/stopwords)
    - Detects if user mentioned "reece" (or variants) to enable smart "recess" matching
    - Scores entities using score_match on those location tokens.
    """
    device = detect_device(text)
    intent = detect_intent(text)
    user_tokens = extract_location_tokens(text, device, intent)
    
    # Check if user mentioned "reece" (or any variant that normalizes to "reece")
    user_text_normalized = " ".join([normalize_token(t) for t in text.lower().split()])
    user_has_reece = "reece" in user_text_normalized
    
    # Hard-coded override: "reece bathroom" or "reece bath" → always match light.bath_recess
    if device == "light" and user_has_reece:
        text_lower = text.lower()
        if ("bathroom" in text_lower or "bath" in text_lower) and "light.bath_recess" in entity_ids:
            return "light.bath_recess"

    best_id, best_score = None, 0.0
    for eid in entity_ids:
        if "." not in eid:
            continue
        _, loc_raw = eid.split(".", 1)
        loc_tokens = loc_raw.replace("_", " ").split()
        s = score_match(user_tokens, loc_tokens, user_has_reece=user_has_reece)
        if s > best_score:
            best_score, best_id = s, eid
    return best_id if best_score >= MIN_SCORE else None

GENERIC_TOKENS = {"light", "lights", "lamp", "bulb", "fan", "ac", "cover", "switch", "room"}


def _humanize_location_from_entity_id(entity_id: str) -> str:
    """
    Best-effort human-readable location from an entity_id like:
    - "light.reece_room" -> "Reece Room"
    - "cover.reece_s_window_blind" -> "Reece's Window Blind"
    """
    if not entity_id or "." not in entity_id:
        return ""
    _, loc_raw = entity_id.split(".", 1)

    # Handle common possessive patterns
    loc_raw = loc_raw.replace("reece_s", "Reece's")
    loc_raw = loc_raw.replace("jake_s", "Jake's")

    parts = loc_raw.split("_")
    pretty_parts: list[str] = []
    for p in parts:
        if not p:
            continue
        # Simple title-case for most tokens
        pretty_parts.append(p.capitalize())

    loc = " ".join(pretty_parts).strip()
    return loc


def _build_response_text(intent: str | None, domain: str | None, entity_id: str | None, parameters: dict) -> str:
    """
    Create a short, human-friendly response like:
    - "Turning on the light in Reece Room."
    - "Opening the cover in Reece's Window Blind."
    """
    if not domain:
        return ""

    loc = _humanize_location_from_entity_id(entity_id or "")
    base = ""

    # Lights
    if domain == "light":
        if intent in {"turn_on", "on", "set_brightness", "set", None, ""}:
            base = "Turning on the light"
        elif intent in {"turn_off", "off"}:
            base = "Turning off the light"

    # Covers
    elif domain == "cover":
        if intent == "set_position" or "position" in parameters:
            base = "Setting cover position"
        elif intent == "open":
            base = "Opening the cover"
        elif intent == "close":
            base = "Closing the cover"

    # Fans
    elif domain == "fan":
        if "percentage" in parameters or "mode" in parameters:
            base = "Setting fan speed"
        elif intent in {"turn_on", "on"}:
            base = "Turning on the fan"
        elif intent in {"turn_off", "off"}:
            base = "Turning off the fan"

    # Climate / AC
    elif domain == "climate":
        if "temperature" in parameters:
            base = "Setting temperature"
        elif intent in {"turn_on", "on"}:
            base = "Turning on the AC"
        elif intent in {"turn_off", "off"}:
            base = "Turning off the AC"

    # If we don't have a concrete target entity, let the caller handle
    # any generic fallback/LLM messaging instead of fabricating one.
    if not base or not entity_id:
        return ""
    
    if loc:
        return f"{base} in {loc}."
    return base + "."


def parse_command(text: str, entity_ids: list[str] | None = None) -> dict:
    """
    Parse a user voice/text command and return structured information.
    
    Args:
        text: User input text (e.g., "turn on lights in reece bathroom")
        entity_ids: Optional list of entity IDs to search. If None, uses ENTITY_IDS.
    
    Returns:
        Dict in the same shape that `VoiceAssistant.execute_command` accepts:
        - {"output_json": {"intent": ..., "domain": ..., "entity_id": ..., "parameters": ..., "response": ...}}
    """
    if entity_ids is None:
        entity_ids = ENTITY_IDS
    
    # Detect device and intent
    device = detect_device(text)  # "light" | "fan" | "climate" | "cover" | None
    intent = detect_intent(text)  # "turn_on" | "turn_off" | "set" | "open" | "close" | ...
    
    # Extract location tokens (text minus intent/device/stopwords)
    location_tokens = extract_location_tokens(text, device, intent)
    
    # Extract parameters (brightness, temperature, fan speed/mode, cover position, etc.)
    parameters = extract_parameters(text, device, intent)
    
    entity_id: str | None = None
    if device:
        # Filter entity_ids by device type if device was detected
        filtered_entity_ids = [
            eid for eid in entity_ids
            if eid.startswith(device + ".")
        ]
        # Find best matching entity_id
        entity_id = best_entity_for_text(text, filtered_entity_ids)

    # Map device -> domain (what VoiceAssistant.execute_command expects)
    domain = device

    # Normalize intent/parameters per-domain to match execute_command expectations
    final_intent = intent or ""
    final_params = parameters or {}

    # Lights: execute_command only accepts turn_on / turn_off
    if domain == "light":
        if final_intent not in {"turn_on", "turn_off", "on", "off"}:
            # Brightness implies turning on with brightness
            final_intent = "turn_on"

    # Covers: support set_position when a percentage is present
    if domain == "cover":
        if "position" in final_params:
            final_intent = "set_position"
        else:
            # Map generic on/off to open/close for covers
            if final_intent in {"turn_on", "on"}:
                final_intent = "open"
            elif final_intent in {"turn_off", "off"}:
                final_intent = "close"

    # Fan: if setting percentage/mode without explicit on/off, keep intent as "set"
    # (FanControl will still apply percentage with state=None)

    # Climate: temperature/mode are handled via parameters; state is inferred only for on/off intents

    # Build human-friendly response. If we are missing intent/domain/entity_id,
    # fall back to a generic clarification message.
    response_text = _build_response_text(final_intent, domain, entity_id, final_params)
    if not final_intent or not domain or not entity_id:
        response_text = "Sorry, please rephrase your query or try again."

    output_json = {
        "intent": final_intent,
        "domain": domain,
        "entity_id": entity_id,
        "parameters": final_params,
        "response": response_text,
    }

    return {"output_json": output_json}


def validate_entity_id(entity_id: str, user_prompt: str) -> bool:
    device = detect_device(user_prompt)
    intent = detect_intent(user_prompt)
    user_tokens = extract_location_tokens(user_prompt, device, intent)
    
    # Check if user mentioned "reece"
    user_text_normalized = " ".join([normalize_token(t) for t in user_prompt.lower().split()])
    user_has_reece = "reece" in user_text_normalized
    
    loc_tokens = entity_id.split('.')[1].replace("_", " ").split()
    cleaned_loc_tokens = []
    for token in loc_tokens:
        if not token in GENERIC_TOKENS:
            cleaned_loc_tokens.append(token)
    score = score_match(user_tokens, cleaned_loc_tokens, user_has_reece=user_has_reece)
    return True if score >= MIN_SCORE else False

if __name__ == "__main__":
    # Simple manual test loop
    while True:
        text = input("Enter a command: ")
        if text.strip().lower() == "exit":
            break
        result = parse_command(text)
        print(result)
        print("-" * 40)