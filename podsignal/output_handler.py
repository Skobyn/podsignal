# podsignal/output_handler.py
"""Writes enriched lead records to CSV or JSON."""

import csv
import json
import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_DIR = "output"


def write_output(leads: list[dict], fmt: str = "csv", output_dir: str = DEFAULT_OUTPUT_DIR) -> str:
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")

    if fmt == "json":
        return _write_json(leads, timestamp, output_dir)
    return _write_csv(leads, timestamp, output_dir)


def _write_csv(leads: list[dict], timestamp: str, output_dir: str) -> str:
    filename = os.path.join(output_dir, f"podsignal_leads_{timestamp}.csv")

    fieldnames = [
        "guest_name", "guest_company", "guest_title",
        "linkedin_url", "guest_stage",
        "podcast_name", "episode_title", "episode_date", "episode_url",
        "prospect_score", "inferred_pain_point", "outreach_trigger",
        "key_topic_1", "key_topic_2", "key_topic_3",
        "key_insight",
        "email_subject", "email_body",
        "reasoning",
    ]

    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for lead in leads:
            s = lead.get("synthesis", {})
            topics = lead.get("key_topics", [])
            email = s.get("email", {})

            writer.writerow({
                "guest_name": lead.get("guest_name", ""),
                "guest_company": lead.get("guest_company", ""),
                "guest_title": lead.get("guest_title", ""),
                "linkedin_url": lead.get("linkedin_url", ""),
                "guest_stage": lead.get("guest_stage", ""),
                "podcast_name": lead.get("podcast_name", ""),
                "episode_title": lead.get("title", ""),
                "episode_date": lead.get("published_str", ""),
                "episode_url": lead.get("episode_url", ""),
                "prospect_score": s.get("prospect_score", ""),
                "inferred_pain_point": s.get("inferred_pain_point", ""),
                "outreach_trigger": s.get("outreach_trigger", ""),
                "key_topic_1": topics[0] if len(topics) > 0 else "",
                "key_topic_2": topics[1] if len(topics) > 1 else "",
                "key_topic_3": topics[2] if len(topics) > 2 else "",
                "key_insight": lead.get("key_insight", ""),
                "email_subject": email.get("subject", ""),
                "email_body": email.get("body", ""),
                "reasoning": s.get("reasoning", ""),
            })

    logger.info("Wrote %d leads to %s", len(leads), filename)
    return filename


def _write_json(leads: list[dict], timestamp: str, output_dir: str) -> str:
    filename = os.path.join(output_dir, f"podsignal_leads_{timestamp}.json")

    # Strip non-serializable fields (e.g. datetime objects) before dump
    clean_leads = []
    for lead in leads:
        clean = {k: v for k, v in lead.items() if k != "published_datetime"}
        clean_leads.append(clean)

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(clean_leads, f, indent=2, default=str)

    logger.info("Wrote %d leads to %s", len(leads), filename)
    return filename
