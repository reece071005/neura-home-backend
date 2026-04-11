import re

# Canonical room names -> list of synonyms/phrases
ROOM_SYNONYMS = {
    "bedroom": [
        "bedroom",
    ],
    "reece bedroom": [
        "reece bedroom",
    ],
    "living room": [
        "living room",
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
    "turn",
    "switch",
    "put",
    "shut",
    "open",
    "close",
    "off",
    "set",
    "kelvin",
    "kelvins",
}

LIGHT_COLOR_NAME_SYNONYMS: dict[str, list[str]] = {
    # Keep these lower-case; matching is done on lower-cased text.
    # Canonical values are passed through as `color_name`.
    "red": ["red"],
    "blue": ["blue"],
    "green": ["green"],
    "yellow": ["yellow"],
    "orange": ["orange"],
    "purple": ["purple", "violet"],
    "pink": ["pink"],
    "white": ["white"],
    "black": ["black"],
    "gray": ["gray", "grey"],
    "brown": ["brown"],
    "cyan": ["cyan"],
    "magenta": ["magenta"],
    "teal": ["teal"],
    "aqua": ["aqua"],
    "lime": ["lime"],
    # Common “near-basic” names people say often
    "turquoise": ["turquoise", "turqoise"],
    "gold": ["gold", "golden"],
    "amber": ["amber"],
}


def _extract_light_color_name(text_lower: str) -> tuple[str | None, set[str]]:
    """
    Best-effort extraction of a spoken color name for lights.

    Returns (color_name, matched_tokens_to_ignore_for_location).
    """
    # Normalize punctuation to spaces so boundary matching behaves.
    t = re.sub(r"[^a-z0-9\s]+", " ", text_lower.lower())
    t = re.sub(r"\s+", " ", t).strip()
    if not t:
        return None, set()

    # Prefer longer (multi-word) phrases if we add any later.
    phrase_candidates: list[tuple[str, str]] = []
    for canonical, syns in LIGHT_COLOR_NAME_SYNONYMS.items():
        for s in syns:
            phrase_candidates.append((canonical, s))
    phrase_candidates.sort(key=lambda x: len(x[1]), reverse=True)

    for canonical, phrase in phrase_candidates:
        # Word-boundary match for single words; works fine for multi-word too.
        if re.search(rf"\b{re.escape(phrase)}\b", t):
            matched_tokens = {normalize_token(tok) for tok in phrase.split() if tok.strip()}
            return canonical, {tok for tok in matched_tokens if tok}

    return None, set()


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

    # If user said a light color (e.g. "red"), don't let it pollute entity matching.
    light_color_tokens: set[str] = set()
    if device == "light":
        _, light_color_tokens = _extract_light_color_name(text_lower)

    cleaned: list[str] = []
    for tok in tokens:
        base = normalize_token(tok)
        if not base:
            continue
        if base in intent_words:
            continue
        if base in device_words:
            continue
        if base in light_color_tokens:
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
        elif "brightness" in text_lower or "bright" in text_lower or "dim" in text_lower:
            # If "dim" mentioned without number, use default dim level
            if "dim" in text_lower:
                params["brightness"] = 40

        color_name, _ = _extract_light_color_name(text_lower)
        if color_name:
            params["color_name"] = color_name

        # Color temperature (Kelvin): "3000 kelvin", "3000K", "set to 3000 k"
        kelvin_match = re.search(r"\b(\d{3,5})\s*(kelvins?|k)\b", text_lower)
        if not kelvin_match:
            # Also allow "color temperature 3000" / "light temperature 3000" without unit
            kelvin_match = re.search(r"\b(?:color temperature|light temperature|temp)\s*(\d{3,5})\b", text_lower)
        if kelvin_match:
            value = int(kelvin_match.group(1))
            # Reasonable safety bounds for spoken light temperature
            value = max(1000, min(value, 20000))
            params["color_temp_kelvin"] = value
            # Enforce exclusivity: kelvin overrides a generic color name if both are mentioned.
            params.pop("color_name", None)
    
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
        if intent in {"turn_on", "on", None, ""} and len(parameters.keys()) == 0:
            base = "Turning on the light"
        elif intent in {"turn_on", "on", "set_temperature", "set_color_temp", "set", "set_color"} and parameters.get("color_temp_kelvin") is not None:
            base = "Setting color temperature of the light to " + str(parameters.get("color_temp_kelvin")) + " Kelvin"
        elif intent in {"turn_on", "on", "set_color", "set_color_name", "set"} and parameters.get("color_name") is not None:
            base = "Setting color of the light to " + parameters.get("color_name")
        elif intent in {"turn_on", "on", "set_brightness", "set_brightness_pct"} and parameters.get("brightness") is not None:
            base = "Setting brightness of the lights to " + str(parameters.get("brightness"))+'%'
        
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
