# podsignal/main.py
"""
PodSignal - Main Orchestrator

Pipeline:
  1. Load target podcasts from podcasts.yaml
  2. Fetch recent episodes from each RSS feed (concurrently)
  3. Claude extracts guest intelligence from episode descriptions
  4. Deduplicate guests across runs
  5. Google finds LinkedIn profiles for each guest
  6. Claude scores fit + drafts personalized outreach emails
  7. Output to CSV / JSON
"""

import os
import sys
import time
import logging
import yaml
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

from podsignal.rss_fetcher import fetch_recent_episodes
from podsignal.guest_extractor import batch_extract_guests
from podsignal.linkedin_finder import enrich_guests_with_linkedin
from podsignal.synthesizer import synthesize_prospect
from podsignal.output_handler import write_output
from podsignal.dedup import load_seen, save_seen, filter_new_guests, mark_seen

load_dotenv()

logger = logging.getLogger(__name__)


def load_config(path: str = "config.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def load_podcasts(path: str = "podcasts.yaml") -> list[dict]:
    with open(path) as f:
        data = yaml.safe_load(f)
    return data.get("podcasts", [])


def _validate_config(config: dict) -> None:
    """Validate required config fields exist."""
    company = config.get("your_company")
    if not company:
        logger.error("Missing 'your_company' section in config.yaml")
        sys.exit(1)
    if not company.get("name"):
        logger.error("Missing 'your_company.name' in config.yaml")
        sys.exit(1)


def run(
    config_path: str = "config.yaml",
    podcasts_path: str = "podcasts.yaml",
    days_back_override: int | None = None,
    min_score_override: int | None = None,
    format_override: str | None = None,
    no_dedup: bool = False,
):
    config = load_config(config_path)
    _validate_config(config)
    podcasts = load_podcasts(podcasts_path)

    search_cfg = config.get("search", {})
    company_cfg = config["your_company"]
    output_cfg = config.get("output", {})
    serpapi_cfg = config.get("serpapi", {})

    days_back = days_back_override if days_back_override is not None else search_cfg.get("days_back", 30)
    max_episodes = search_cfg.get("max_episodes_per_show", 20)
    min_score = min_score_override if min_score_override is not None else output_cfg.get("min_score", 6)
    output_format = format_override if format_override is not None else output_cfg.get("format", "csv")
    model = config.get("model") or os.environ.get("PODSIGNAL_MODEL")

    use_serpapi = serpapi_cfg.get("enabled", False)
    serpapi_key = serpapi_cfg.get("api_key") or os.environ.get("SERPAPI_KEY")

    logger.info("PodSignal starting...")
    logger.info("  Company: %s", company_cfg["name"])
    logger.info("  Podcasts: %d shows", len(podcasts))
    logger.info("  Looking back: %d days", days_back)
    logger.info("  Min score to output: %d/10", min_score)

    # --- Phase 1: Fetch episodes from all shows (concurrently) ---
    all_guests = []

    def _fetch_and_extract(podcast):
        """Fetch episodes + extract guests for one podcast."""
        name = podcast.get("name", "?")
        logger.info("Fetching %s...", name)
        episodes = fetch_recent_episodes(podcast, days_back=days_back, max_episodes=max_episodes)
        logger.info("  %s: %d recent episodes", name, len(episodes))
        if not episodes:
            return []
        guests = batch_extract_guests(episodes, model=model)
        logger.info("  %s: %d guests extracted", name, len(guests))
        return guests

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(_fetch_and_extract, p): p for p in podcasts}
        for future in as_completed(futures):
            try:
                all_guests.extend(future.result())
            except Exception as e:
                podcast = futures[future]
                logger.error("Failed processing %s: %s", podcast.get("name", "?"), e)

    logger.info("Total guests found across all shows: %d", len(all_guests))

    if not all_guests:
        logger.info("No guests found. Try increasing days_back or adding more podcasts.")
        return []

    # --- Phase 1.5: Deduplication ---
    if not no_dedup:
        seen = load_seen()
        all_guests = filter_new_guests(all_guests, seen)
        if not all_guests:
            logger.info("All guests already seen in previous runs. Nothing new to process.")
            return []

    # --- Phase 2: Find LinkedIn profiles ---
    logger.info("Finding LinkedIn profiles...")
    all_guests = enrich_guests_with_linkedin(
        all_guests,
        use_serpapi=use_serpapi,
        serpapi_key=serpapi_key,
    )

    # --- Phase 3: Score + synthesize outreach ---
    logger.info("Synthesizing %d leads with Claude...", len(all_guests))

    qualified_leads = []

    for guest in all_guests:
        name = guest.get("guest_name", "Unknown")
        logger.info("  Scoring %s (%s)", name, guest.get("podcast_name", ""))

        try:
            synthesis = synthesize_prospect(guest, company_cfg, model=model)
            score = synthesis.get("prospect_score", 0)

            logger.info("    Score: %d/10 - %s", score, synthesis.get("reasoning", "")[:70])

            if score >= min_score:
                guest["synthesis"] = synthesis
                qualified_leads.append(guest)
                logger.info("    Qualified!")

        except Exception as e:
            logger.error("    Error scoring %s: %s", name, e)

        time.sleep(0.5)

    logger.info("%d qualified leads (score >= %d)", len(qualified_leads), min_score)

    # --- Phase 4: Output ---
    if qualified_leads:
        output_file = write_output(qualified_leads, fmt=output_format)
        logger.info("Output: %s", output_file)
    else:
        logger.info("No leads met the minimum score. Try lowering min_score in config.yaml.")

    # --- Phase 5: Update dedup tracking ---
    if not no_dedup:
        seen = mark_seen(all_guests, seen)
        save_seen(seen)

    return qualified_leads


if __name__ == "__main__":
    from podsignal.utils import setup_logging
    setup_logging()
    run()
