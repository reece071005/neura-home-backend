# app/voice/device_matcher.py
"""
Match user voice/text (e.g. "turn on lights in Reece's bedroom") to a specific
entity_id from controllable_devices using embedding similarity.
"""

import json
import logging
from typing import Optional

import aiohttp

from app.config import EMBED_API_URL, EMBED_MODEL
from app.core.redis_init import get_redis

logger = logging.getLogger(__name__)

EMBED_CACHE_PREFIX = "embed:"
EMBED_CACHE_TTL = 86400  # 24h

# Fallback models to try if the configured one is not pulled (404)
EMBED_MODEL_FALLBACKS = ("nomic-embed-text", "mxbai-embed-large", "all-minilm")

# Homophones / common mishearings: query word -> entity words that should count as a match
# e.g. "recess" (voice) often means "Reece's"
QUERY_TO_ENTITY_ALIASES = {
    "recess": ["reece", "reeces"],
    "reece": ["reece", "reeces"],
    "jakes": ["jake", "jakes"],
    "jake": ["jake", "jakes"],
}

# Room-type words: if user says one of these, we boost entities containing the key, penalize conflicting
ROOM_KEYWORDS = {"bedroom", "bathroom", "room", "kitchen", "living", "study", "guest", "master", "kids", "lounge", "dining", "laundry", "garage", "patio", "balcony", "hall", "hallway", "staircase"}


def _entity_id_to_search_text(entity_id: str) -> str:
    """Convert entity_id to a searchable phrase for embedding. E.g. light.reece_room -> reece room light."""
    if "." not in entity_id:
        return entity_id.replace("_", " ")
    domain, name = entity_id.split(".", 1)
    # "light.reece_room" -> "reece room light"; "cover.study_blind" -> "study blind cover"
    words = name.replace("_", " ").strip().split()
    return " ".join(words) + " " + domain


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or len(a) == 0:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _keyword_score_adjustment(user_text: str, entity_id: str, search_text: str) -> float:
    """
    Adjust embedding score using location/room keywords so e.g. "recess bedroom"
    prefers reece_room over bath_recess. Returns a delta to add to similarity (-0.3 to +0.25).
    """
    user_lower = user_text.lower().strip()
    user_words = set(user_lower.replace("'", "").replace("'", "").split())
    search_lower = search_text.lower()
    entity_lower = entity_id.lower()
    delta = 0.0

    # If user said "bedroom" (or "recess bedroom" = Reece's bedroom), strongly prefer entities with "room"
    if "bedroom" in user_words or "room" in user_words:
        has_room = "room" in search_lower or "bedroom" in search_lower
        has_bath_no_room = ("bath" in search_lower or "recess" in search_lower) and not has_room
        if has_bath_no_room:
            delta -= 0.35  # e.g. bath_recess for "bedroom" -> penalize
        elif has_room:
            delta += 0.15  # reece_room, master_bedroom etc. -> boost

    # Homophones: "recess" in query -> boost entities with "reece"
    for query_word, entity_words in QUERY_TO_ENTITY_ALIASES.items():
        if query_word in user_words:
            if any(w in search_lower or w in entity_lower for w in entity_words):
                delta += 0.2
            break

    # General room-type match: user said kitchen/living/study etc. and entity has it
    for kw in ROOM_KEYWORDS:
        if kw in user_words and kw in search_lower:
            delta += 0.1
            break

    return delta


async def get_embedding(text: str) -> Optional[list[float]]:
    """Get embedding vector for text from Ollama (or other embed API). Tries fallback models on 404."""
    if not text or not text.strip():
        return None
    models_to_try = (EMBED_MODEL,) + tuple(m for m in EMBED_MODEL_FALLBACKS if m != EMBED_MODEL)
    last_error = None
    for model in models_to_try:
        payload = {"model": model, "prompt": text.strip()}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(EMBED_API_URL, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    body = await resp.text()
                    if resp.status == 200:
                        try:
                            data = json.loads(body)
                        except json.JSONDecodeError:
                            return None
                        return data.get("embedding")
                    if resp.status == 404:
                        last_error = f'model "{model}" not found'
                        logger.info("Embed model %s not available, trying next. Run: ollama pull %s", model, model)
                        continue
                    logger.warning("Embed API status %s: %s", resp.status, body)
                    last_error = body
        except Exception as e:
            last_error = str(e)
            logger.warning("Embed request failed: %s", e)
    if last_error:
        logger.warning(
            "No embedding model available. Pull one with: ollama pull nomic-embed-text (or set EMBED_MODEL). %s",
            last_error,
        )
    return None


async def _get_cached_embedding(entity_id: str) -> Optional[list[float]]:
    redis = get_redis()
    key = EMBED_CACHE_PREFIX + entity_id
    raw = await redis.get(key)
    if raw:
        try:
            return json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            pass
    text = _entity_id_to_search_text(entity_id)
    emb = await get_embedding(text)
    if emb is not None:
        await redis.setex(key, EMBED_CACHE_TTL, json.dumps(emb))
    return emb


TOP_K_CANDIDATES = 5


async def match_entity(
    user_text: str,
    entity_ids: list[str],
    device_hint: Optional[str] = None,
    top_k: int = TOP_K_CANDIDATES,
) -> list[str]:
    """
    Match user phrase to the best entity_ids using embedding similarity.
    Returns up to top_k candidates (default 5), best first.
    Optionally filter candidates by domain (light, fan, cover, climate).
    """
    if not entity_ids or not user_text or not user_text.strip():
        return []

    # Filter by domain if we know device type
    candidates = entity_ids
    if device_hint:
        domain = device_hint.strip().lower()
        if domain in ("light", "fan", "cover", "climate", "switch"):
            candidates = [e for e in entity_ids if e.startswith(domain + ".")]
        if not candidates:
            candidates = entity_ids

    if len(candidates) <= top_k:
        return candidates[:]

    query_embedding = await get_embedding(user_text)
    if query_embedding is None:
        # Fallback: simple substring match, return top_k by score
        user_lower = user_text.lower().replace("'", "").replace("'", "")
        scored: list[tuple[float, str]] = []
        for eid in candidates:
            search_text = _entity_id_to_search_text(eid).lower()
            score = sum(1 for w in user_lower.split() if w in search_text or w in eid)
            scored.append((score, eid))
        scored.sort(key=lambda x: -x[0])
        return [eid for _, eid in scored[:top_k]] if scored else candidates[:top_k]

    scored: list[tuple[float, str]] = []
    for entity_id in candidates:
        emb = await _get_cached_embedding(entity_id)
        if emb is None:
            continue
        sim = _cosine_similarity(query_embedding, emb)
        search_text = _entity_id_to_search_text(entity_id)
        sim += _keyword_score_adjustment(user_text, entity_id, search_text)
        scored.append((sim, entity_id))

    scored.sort(key=lambda x: -x[0])
    return [eid for _, eid in scored[:top_k]]
