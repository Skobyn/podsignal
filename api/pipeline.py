"""
PodSignal Pipeline Adapter

Wraps the existing podsignal CLI pipeline for async API use.
"""

import asyncio
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))


async def run_pipeline_async(config: dict, podcasts: list, job_id: str, jobs: dict) -> list:
    """
    Run the podsignal pipeline in a thread pool (it's synchronous).
    Updates job progress as it goes.
    """
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        _run_sync,
        config, podcasts, job_id, jobs
    )
    return result


def _run_sync(config: dict, podcasts: list, job_id: str, jobs: dict) -> list:
    """
    Synchronous pipeline runner — called from thread pool.
    """
    try:
        from podsignal.rss_fetcher import fetch_recent_episodes
        from podsignal.guest_extractor import batch_extract_guests
        from podsignal.linkedin_finder import enrich_guests_with_linkedin
        from podsignal.synthesizer import synthesize_prospect

        search_cfg = config.get("search", {})
        company_cfg = config["your_company"]
        output_cfg = config.get("output", {})

        days_back = search_cfg.get("days_back", 30)
        max_episodes = search_cfg.get("max_episodes_per_show", 15)
        min_score = output_cfg.get("min_score", 5)

        all_guests = []

        jobs[job_id]["progress"] = 30
        jobs[job_id]["status_message"] = "Fetching podcast episodes..."

        for i, podcast in enumerate(podcasts):
            try:
                name = podcast.get("name", "?")
                logger.info(f"[{job_id}] Fetching {name}...")
                episodes = fetch_recent_episodes(podcast, days_back=days_back, max_episodes=max_episodes)
                if episodes:
                    guests = batch_extract_guests(episodes)
                    all_guests.extend(guests)
                    logger.info(f"[{job_id}] {name}: {len(guests)} guests")
            except Exception as e:
                logger.error(f"[{job_id}] Error processing {podcast.get('name', '?')}: {e}")

            # Update progress
            progress = 30 + int((i + 1) / len(podcasts) * 30)
            jobs[job_id]["progress"] = progress

        logger.info(f"[{job_id}] Total guests: {len(all_guests)}")

        if not all_guests:
            return []

        jobs[job_id]["progress"] = 60
        jobs[job_id]["status_message"] = "Finding LinkedIn profiles..."

        # Enrich with LinkedIn (skip to save API calls if no serpapi key)
        try:
            all_guests = enrich_guests_with_linkedin(all_guests, use_serpapi=False)
        except Exception as e:
            logger.warning(f"[{job_id}] LinkedIn enrichment failed: {e}")

        jobs[job_id]["progress"] = 70
        jobs[job_id]["status_message"] = "Scoring and synthesizing leads..."

        qualified = []
        for guest in all_guests:
            try:
                synthesis = synthesize_prospect(guest, company_cfg)
                score = synthesis.get("prospect_score", 0)
                if score >= min_score:
                    guest["synthesis"] = synthesis
                    guest["score"] = score
                    qualified.append(guest)
            except Exception as e:
                # Score 5 by default if synthesis fails
                guest["score"] = 5
                guest["synthesis"] = {
                    "prospect_score": 5,
                    "reasoning": "Score unavailable",
                    "outreach_email": "",
                    "subject_line": f"Saw your episode on {guest.get('podcast_name', 'the podcast')}",
                }
                qualified.append(guest)

        jobs[job_id]["progress"] = 80
        logger.info(f"[{job_id}] {len(qualified)} qualified leads")
        return qualified

    except Exception as e:
        logger.error(f"[{job_id}] Pipeline sync error: {e}", exc_info=True)
        raise
