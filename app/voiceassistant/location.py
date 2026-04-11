"""
Handle voice queries about resident location (e.g. "where is Reece", "where are my kids").
Uses DetectionNotification data from the vision surveillance system.
"""
import re
from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app import models


# Phrases that indicate a location query
LOCATION_QUERY_PATTERNS = [
    r"\bwhere\s+(is|are)\b",
    r"\bwhere('s|s)\s+",
    r"\blocation\s+of\b",
    r"\bfind\s+(my\s+)?",
    r"\bwhere\s+did\s+.+\s+go\b",
    r"\bwhere\s+.+\s+last\s+seen\b",
]

# Map user query targets to detection message labels (for matching)
# "kids" / "children" / "my kids" -> matches "Kid is detected at..."
KID_ALIASES = {"kid", "kids", "children", "child"}

# Phrases that indicate a geographical/place question (not a resident) -> pass to LLM
PLACE_INDICATORS = [
    "located",
    "in the world",
    "on earth",
    "on the map",
    "geographically",
    "country",
    "countries",
    "city",
    "cities",
    "capital",
    "continent",
    "coordinates",
    "latitude",
    "longitude",
    "distance from",
]

# Delivery-related keywords (for recent delivery queries)
DELIVERY_KEYWORDS = {
    "delivery",
    "deliveries",
    "package",
    "packages",
    "parcel",
    "parcels",
    "courier",
    "couriers",
    "amazon",
    "ups",
    "fedex",
}


def is_location_query(text: str) -> bool:
    """Return True if the text appears to be asking about a resident's location in the house."""
    if not text or not text.strip():
        return False
    t = text.lower().strip()
    # Exclude geographical/place questions - these should go to the LLM
    for phrase in PLACE_INDICATORS:
        if phrase in t:
            return False
    for pattern in LOCATION_QUERY_PATTERNS:
        if re.search(pattern, t, re.IGNORECASE):
            return True
    return False


def is_delivery_query(text: str) -> bool:
    """Return True if the text appears to be asking about deliveries/packages."""
    if not text or not text.strip():
        return False
    t = text.lower()
    return any(kw in t for kw in DELIVERY_KEYWORDS)


async def get_resident_names(db: AsyncSession) -> set[str]:
    """
    Return a set of known resident names (lowercased) based on Userface records.
    These represent current residents configured in the system.
    """
    result = await db.execute(select(models.Userface.name))
    rows = result.all()
    names: set[str] = set()
    for (name,) in rows:
        if name:
            names.add(name.lower())
    return names


def extract_location_target(text: str) -> str | None:
    """
    Extract the person/group the user is asking about.
    Returns lowercase name or "kids" for child-related queries.
    Examples:
      "where is reece" -> "reece"
      "where are my kids" -> "kids"
      "where is ahmad" -> "ahmad"
      "where is max" -> "max"
    """
    if not text or not text.strip():
        return None
    t = text.lower().strip()
    tokens = re.split(r"\s+", t)

    # Remove common leading words and contractions
    skip = {
        "where",
        "wheres",
        "what",
        "location",
        "of",
        "the",
        "my",
        "is",
        "are",
        "find",
        "did",
        "go",
        "a",
    }
    remaining = [w for w in tokens if re.sub(r"[^a-z]+", "", w.lower()) not in skip]

    if not remaining:
        return None

    # "where are my kids" -> kids
    for w in remaining:
        n = re.sub(r"[^a-z]+", "", w)
        if n in KID_ALIASES:
            return "kids"

    # First remaining token is typically the name: "where is reece" -> reece
    first = remaining[0]
    return re.sub(r"[^a-z]+", "", first) if first else None


def _parse_detection_message(message: str) -> tuple[str, str] | None:
    """
    Parse a detection message like "Reece is detected at front door" or "Kid is detected at garage".
    Returns (person_label, location) or None.
    """
    # "Name is detected at location"
    m = re.match(r"^(.+?)\s+is\s+detected\s+at\s+(.+)$", message, re.IGNORECASE)
    if m:
        person, loc = m.group(1).strip(), m.group(2).strip()
        return (person, loc)
    # "Delivery person detected at X" / "Stranger detected at X" - less relevant for residents
    m = re.match(r"^(.+?)\s+detected\s+at\s+(.+)$", message, re.IGNORECASE)
    if m:
        person, loc = m.group(1).strip(), m.group(2).strip()
        return (person, loc)
    return None


def _person_matches_target(parsed_person: str, target: str) -> bool:
    """Check if parsed person from detection matches the user's query target."""
    target = target.lower()
    parsed_lower = parsed_person.lower()

    if target == "kids":
        return parsed_lower == "kid"

    # Direct name match: "reece" matches "Reece"
    return parsed_lower == target


async def get_recent_detections(
    db: AsyncSession,
    max_count: int = 50,
    max_age_hours: float = 24.0,
) -> list[dict[str, Any]]:
    """
    Fetch recent detection notifications from the database.
    Returns list of dicts with keys: message, camera_entity, created_at, parsed (person, location).
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    stmt = (
        select(models.DetectionNotification)
        .where(models.DetectionNotification.created_at >= cutoff)
        .order_by(models.DetectionNotification.created_at.desc())
        .limit(max_count)
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()

    out = []
    for r in rows:
        parsed = _parse_detection_message(r.message)
        out.append({
            "message": r.message,
            "camera_entity": r.camera_entity,
            "created_at": r.created_at,
            "parsed": parsed,
        })
    return out


def _format_timestamp(ts: datetime) -> str:
    """Format datetime as human-readable time string (e.g., 'at 2:30 PM')."""
    if not ts.tzinfo:
        ts = ts.replace(tzinfo=timezone.utc)
    # Convert to local time (assuming UTC for now, can be adjusted)
    local_ts = ts.astimezone()
    # Format as 12-hour time with AM/PM
    return local_ts.strftime("%I:%M %p").lstrip("0")


def format_location_response(
    detections: list[dict[str, Any]],
    target: str,
) -> str:
    """
    Format a natural language response from detection data for the given target.
    """
    if target == "kids":
        matches = [d for d in detections if d.get("parsed") and _person_matches_target(d["parsed"][0], "kids")]
        if not matches:
            return "I haven't seen any kids recently on the cameras."
        # Dedupe by location, keep most recent
        seen: dict[str, tuple[datetime, str]] = {}
        for m in matches:
            _, loc = m["parsed"]
            ts = m["created_at"]
            if loc not in seen or ts > seen[loc][0]:
                seen[loc] = (ts, loc)
        locs_info = list(seen.values())
        if len(locs_info) == 1:
            ts, loc = locs_info[0]
            exact_time = _format_timestamp(ts)
            return f"A kid was last seen at the {loc} at {exact_time}."
        # Multiple locations - format each with time
        parts = []
        for ts, loc in locs_info:
            exact_time = _format_timestamp(ts)
            parts.append(f"the {loc} at {exact_time}")
        return f"Kids were last seen at {', and at '.join(parts)}."
    else:
        matches = [d for d in detections if d.get("parsed") and _person_matches_target(d["parsed"][0], target)]
        if not matches:
            return f"I haven't seen {target.title()} recently on the cameras."
        # Most recent
        m = matches[0]
        _, loc = m["parsed"]
        ts = m["created_at"]
        exact_time = _format_timestamp(ts)
        now = datetime.now(timezone.utc)
        diff = now - (ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc))
        mins = int(diff.total_seconds() / 60)
        if mins < 2:
            time_ago = "just now"
        elif mins < 60:
            time_ago = f"about {mins} minutes ago"
        else:
            hours = int(mins / 60)
            time_ago = f"about {hours} hour{'s' if hours != 1 else ''} ago"
        return f"{m['parsed'][0]} was last seen at the {loc} at {exact_time} ({time_ago})."


def format_delivery_response(detections: list[dict[str, Any]]) -> str:
    """
    Format a response about recent deliveries based on detection data.
    """
    matches = [
        d
        for d in detections
        if d.get("parsed") and "delivery" in d["parsed"][0].lower()
    ]
    if not matches:
        return "There haven't been any recent deliveries on the cameras."

    # Most recent delivery
    m = matches[0]
    _, loc = m["parsed"]
    ts = m["created_at"]
    exact_time = _format_timestamp(ts)
    now = datetime.now(timezone.utc)
    diff = now - (ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc))
    mins = int(diff.total_seconds() / 60)
    if mins < 2:
        time_ago = "just now"
    elif mins < 60:
        time_ago = f"about {mins} minutes ago"
    else:
        hours = int(mins / 60)
        time_ago = f"about {hours} hour{'s' if hours != 1 else ''} ago"

    return f"A delivery person was last seen at the {loc} at {exact_time} ({time_ago})."


async def query_resident_location(text: str, db: AsyncSession) -> str:
    """
    Main entry: if this is a location query, fetch detection data and return a response.
    Returns the response string, or empty string if this was not a location query.
    """
    if not is_location_query(text):
        return ""

    target = extract_location_target(text)
    if not target:
        return ""  # Let LLM handle vague queries

    # Fetch recent detections and known resident names
    detections = await get_recent_detections(db)
    resident_names = await get_resident_names(db)

    # Also include any named residents from detection messages (excluding generic labels)
    for d in detections:
        if not d.get("parsed"):
            continue
        person, _ = d["parsed"]
        pl = person.lower()
        if pl not in {"kid", "delivery person", "stranger"}:
            resident_names.add(pl)

    # Only answer resident location queries for configured residents or kids
    if target != "kids" and target not in resident_names:
        # Not a known resident – let the LLM handle (e.g., "where is Moscow located")
        return ""

    return format_location_response(detections, target)


async def query_delivery_status(text: str, db: AsyncSession) -> str:
    """
    Handle queries about recent deliveries/packages.
    Returns response string, or empty string if not a delivery-related query.
    """
    if not is_delivery_query(text):
        return ""

    detections = await get_recent_detections(db)
    return format_delivery_response(detections)

