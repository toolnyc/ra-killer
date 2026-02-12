from __future__ import annotations

import json
import random

import anthropic

from src.config import settings
from src.log import get_logger
from src.models import Event
from src.recommend.taste import TasteProfile

logger = get_logger("scorer")


def heuristic_score(event: Event, taste: TasteProfile) -> float:
    """Fast heuristic score. Returns a numeric score."""
    score = 0.0

    # Artist matches: +30 per known artist
    for artist in event.artists:
        w = taste.artist_weight(artist)
        if w > 0:
            score += 30 * w
        elif w < 0:
            score += 15 * w  # penalty for disliked artists

    # Venue match: +20
    if event.venue_name:
        w = taste.venue_weight(event.venue_name)
        if w > 0:
            score += 20 * w
        elif w < 0:
            score += 10 * w

    # Attending count bonus (log scale)
    if event.attending_count and event.attending_count > 0:
        import math
        score += min(10, math.log2(event.attending_count + 1) * 2)

    # Price penalty: more expensive = small penalty
    if event.price_min_cents and event.price_min_cents > 5000:  # > $50
        score -= 5

    return score


def heuristic_prefilter(
    events: list[Event], taste: TasteProfile, discovery_count: int = 15
) -> tuple[list[tuple[Event, float]], list[Event]]:
    """Score events heuristically.

    Returns:
        (scored_events, discovery_events)
        scored_events: events with score > 0, sorted by score
        discovery_events: up to discovery_count events at score 0 for Claude
    """
    scored = []
    unknown = []

    for event in events:
        s = heuristic_score(event, taste)
        if s > 0:
            scored.append((event, s))
        else:
            unknown.append(event)

    scored.sort(key=lambda x: -x[1])

    # Take a random sample of unknowns for discovery
    discovery = random.sample(unknown, min(discovery_count, len(unknown)))

    return scored, discovery


async def claude_batch_score(
    events: list[Event],
    taste: TasteProfile,
    past_feedback: list[dict] | None = None,
) -> list[dict]:
    """Score events using Claude. Returns list of {event_id, score, reasoning, tags}.

    Sends all events in a single API call for cost efficiency.
    """
    if not events:
        return []

    if not settings.anthropic_api_key:
        logger.warning("no_anthropic_key", msg="Skipping Claude scoring")
        return []

    # Build event descriptions
    event_texts = []
    for i, e in enumerate(events):
        artists_str = ", ".join(e.artists) if e.artists else "Unknown"
        text = (
            f"[{i}] {e.title}\n"
            f"  Date: {e.event_date}\n"
            f"  Venue: {e.venue_name or 'Unknown'}\n"
            f"  Artists: {artists_str}\n"
            f"  Price: {e.cost_display or 'Unknown'}\n"
            f"  Attending: {e.attending_count or 'Unknown'}\n"
            f"  Sources: {', '.join(e.sources)}\n"
            f"  Description: {(e.description or '')[:200]}"
        )
        event_texts.append(text)

    # Build feedback examples
    feedback_text = ""
    if past_feedback:
        examples = []
        for fb in past_feedback[:20]:
            ev = fb.get("events", {})
            status = fb.get("feedback", "no response")
            examples.append(f"  - {ev.get('title', '?')} at {ev.get('venue_name', '?')}: {status}")
        if examples:
            feedback_text = "\n\nPast feedback (approved = user liked, rejected = user didn't):\n" + "\n".join(examples)

    prompt = f"""You are a nightlife recommendation engine for a NYC music fan. Score each event 0-100 based on how well it matches this taste profile.

## Taste Profile
{taste.to_prompt_text()}
{feedback_text}

## Events to Score
{chr(10).join(event_texts)}

Return a JSON array with one object per event:
[{{"index": 0, "score": 75, "reasoning": "one sentence why", "tags": ["house", "brooklyn"]}}]

Rules:
- Score 80-100: Strong match (known favorite artists/venues)
- Score 50-79: Likely match (similar style, good venue, interesting lineup)
- Score 20-49: Possible match (some relevant elements)
- Score 0-19: Poor match (disliked venue, uninteresting lineup, etc.)
- Be generous with discovery: unknown-but-promising events should get 40-60
- Return ONLY valid JSON, no markdown fences"""

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    try:
        response = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()

        # Parse JSON response
        # Handle potential markdown fences
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]

        results = json.loads(text)

        # Map back to events
        scored = []
        for r in results:
            idx = r.get("index", 0)
            if 0 <= idx < len(events):
                scored.append(
                    {
                        "event_id": events[idx].id,
                        "score": r.get("score", 0),
                        "reasoning": r.get("reasoning", ""),
                        "tags": r.get("tags", []),
                    }
                )

        logger.info("claude_scoring_complete", count=len(scored))
        return scored

    except Exception as e:
        logger.error("claude_scoring_failed", error=str(e))
        return []
