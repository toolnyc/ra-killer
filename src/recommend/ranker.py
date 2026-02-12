from __future__ import annotations

from src import db
from src.log import get_logger
from src.models import Event, Recommendation
from src.recommend.scorer import claude_batch_score, heuristic_prefilter
from src.recommend.taste import TasteProfile

logger = get_logger("ranker")


async def rank_events(
    events: list[Event],
    taste: TasteProfile | None = None,
    top_n: int = 10,
    use_claude: bool = True,
) -> list[Recommendation]:
    """Full ranking pipeline: heuristic pre-filter -> Claude scoring -> top N.

    Returns list of Recommendation objects (not yet saved to DB).
    """
    if taste is None:
        taste = TasteProfile()

    # Phase 1: Heuristic pre-filter
    scored_events, discovery_events = heuristic_prefilter(events, taste)
    logger.info(
        "prefilter_done",
        scored=len(scored_events),
        discovery=len(discovery_events),
    )

    if not use_claude or not scored_events and not discovery_events:
        # Just use heuristic scores
        recs = []
        for event, score in scored_events[:top_n]:
            recs.append(
                Recommendation(
                    event_id=event.id,
                    score=score,
                    reasoning="Heuristic match based on known artists/venues",
                )
            )
        return recs

    # Phase 2: Claude batch scoring
    # Send top heuristic matches + discovery batch
    candidates = [e for e, _ in scored_events[:50]] + discovery_events
    past_feedback = db.get_recent_recommendations(limit=50)

    claude_scores = await claude_batch_score(candidates, taste, past_feedback)

    if not claude_scores:
        # Fallback to heuristic only
        recs = []
        for event, score in scored_events[:top_n]:
            recs.append(
                Recommendation(
                    event_id=event.id,
                    score=score,
                    reasoning="Heuristic match (Claude unavailable)",
                )
            )
        return recs

    # Merge heuristic + Claude scores (weighted average)
    heuristic_map = {e.id: s for e, s in scored_events}
    max_h = max(heuristic_map.values(), default=1)
    final_scores: list[dict] = []

    for cs in claude_scores:
        eid = cs["event_id"]
        claude_score = cs["score"]
        heuristic = heuristic_map.get(eid, 0)

        # Weighted: 70% Claude, 30% heuristic (normalized to 0-100)
        h_normalized = min(100, (heuristic / max_h) * 100) if max_h > 0 else 0
        combined = claude_score * 0.7 + h_normalized * 0.3

        final_scores.append(
            {
                "event_id": eid,
                "score": combined,
                "reasoning": cs.get("reasoning", ""),
            }
        )

    # Sort and take top N
    final_scores.sort(key=lambda x: -x["score"])

    recs = []
    for fs in final_scores[:top_n]:
        recs.append(
            Recommendation(
                event_id=fs["event_id"],
                score=fs["score"],
                reasoning=fs["reasoning"],
            )
        )

    logger.info("ranking_complete", recommendations=len(recs))
    return recs


async def run_training_pipeline(
    days_back: int = 60,
    top_n: int = 10,
    exclude_recommended: bool = True,
) -> list[Recommendation]:
    """Score past events for training — lets the user give feedback to refine taste."""
    events = db.get_past_events(days_back)
    if not events:
        logger.warning("no_past_events", msg="No past events found for training")
        return []

    if exclude_recommended:
        already = db.get_recommended_event_ids()
        events = [e for e in events if e.id not in already]
        if not events:
            logger.info("all_past_events_already_recommended")
            return []

    taste = TasteProfile()
    recs = await rank_events(events, taste, top_n=top_n)

    for rec in recs:
        rec_id = db.save_recommendation(rec)
        rec.id = rec_id

    logger.info("training_pipeline_complete", count=len(recs))
    return recs


async def run_recommendation_pipeline(top_n: int = 10) -> list[Recommendation]:
    """Full pipeline: load events, load taste, rank, save recommendations."""
    events = db.get_upcoming_events()
    if not events:
        logger.warning("no_events", msg="No upcoming events to rank")
        return []

    taste = TasteProfile()
    recs = await rank_events(events, taste, top_n=top_n)

    # Save to DB
    for rec in recs:
        rec_id = db.save_recommendation(rec)
        rec.id = rec_id

    logger.info("recommendation_pipeline_complete", count=len(recs))
    return recs
