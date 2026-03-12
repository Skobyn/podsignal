"""
PodSignal Web API — FastAPI backend

Exposes the podcast guest intelligence pipeline as a REST API.
Also serves the React frontend in production.
"""

import os
import sys
import uuid
import json
import logging
import asyncio
from pathlib import Path
from typing import Optional
from datetime import datetime

from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Add parent dir to path so we can import the podsignal pipeline
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.geocoder import geocode_guest
from api.pipeline import run_pipeline_async

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="PodSignal", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory job store (replace with Firestore for persistence)
jobs: dict = {}
cached_guests: list = []

RESULTS_DIR = Path("/tmp/podsignal_results")
RESULTS_DIR.mkdir(exist_ok=True)


# ─── Request Models ───────────────────────────────────────────────────────────

class SearchRequest(BaseModel):
    keyword: str
    rss_feeds: Optional[list[dict]] = None  # [{"name": "...", "rss": "..."}]
    days_back: Optional[int] = 30
    min_score: Optional[int] = 5
    company_name: Optional[str] = None
    company_description: Optional[str] = None
    company_pitch: Optional[str] = None


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {"status": "ok", "version": "2.0.0"}


@app.post("/api/search")
async def search(req: SearchRequest, background_tasks: BackgroundTasks):
    """Start a podcast search job. Returns a job_id to poll for results."""
    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {
        "id": job_id,
        "status": "running",
        "keyword": req.keyword,
        "created_at": datetime.utcnow().isoformat(),
        "progress": 0,
        "guests": [],
        "error": None,
    }
    background_tasks.add_task(run_job, job_id, req)
    return {"job_id": job_id, "status": "running"}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    """Poll job status and results."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return jobs[job_id]


@app.get("/api/guests")
def get_all_guests():
    """Return all cached guests from all previous runs."""
    return {"guests": cached_guests, "count": len(cached_guests)}


@app.get("/api/jobs")
def list_jobs():
    """List all jobs."""
    return {"jobs": list(jobs.values())}


# ─── Background job runner ────────────────────────────────────────────────────

async def run_job(job_id: str, req: SearchRequest):
    """Run the pipeline in the background and update job state."""
    try:
        jobs[job_id]["progress"] = 10
        logger.info(f"[{job_id}] Starting pipeline for keyword: {req.keyword}")

        # Build config for the pipeline
        config = {
            "your_company": {
                "name": req.company_name or "Get Apex Insights",
                "description": req.company_description or "Marketing and Operations intelligence for Restaurants",
                "pitch": req.company_pitch or "We help operators understand what's actually driving growth",
            },
            "search": {
                "days_back": req.days_back,
                "max_episodes_per_show": 15,
            },
            "output": {
                "min_score": req.min_score,
                "format": "json",
            },
        }

        # Build podcast list: use provided feeds or keyword-based discovery
        if req.rss_feeds:
            podcasts = req.rss_feeds
        else:
            # Use the keyword to find relevant RSS feeds via PodcastIndex/iTunes
            podcasts = await discover_podcasts(req.keyword)

        if not podcasts:
            jobs[job_id]["status"] = "done"
            jobs[job_id]["error"] = "No podcast feeds found for this keyword. Try providing RSS feeds directly."
            return

        jobs[job_id]["progress"] = 20
        jobs[job_id]["podcast_count"] = len(podcasts)

        # Run the pipeline
        leads = await run_pipeline_async(config, podcasts, job_id, jobs)

        jobs[job_id]["progress"] = 85
        logger.info(f"[{job_id}] Got {len(leads)} leads, geocoding...")

        # Geocode each guest
        geocoded = []
        for guest in leads:
            try:
                geo = await geocode_guest(guest)
                if geo:
                    guest["lat"] = geo["lat"]
                    guest["lng"] = geo["lng"]
                    guest["location_name"] = geo["name"]
                    guest["location_resolved"] = True
                else:
                    guest["lat"] = None
                    guest["lng"] = None
                    guest["location_name"] = None
                    guest["location_resolved"] = False
            except Exception as e:
                logger.warning(f"Geocoding failed for {guest.get('guest_name')}: {e}")
                guest["lat"] = None
                guest["lng"] = None
            geocoded.append(guest)

        jobs[job_id]["guests"] = geocoded
        jobs[job_id]["status"] = "done"
        jobs[job_id]["progress"] = 100
        jobs[job_id]["completed_at"] = datetime.utcnow().isoformat()

        # Add to global cache
        cached_guests.extend(geocoded)

        logger.info(f"[{job_id}] Done. {len(geocoded)} guests, {sum(1 for g in geocoded if g.get('lat'))} geocoded.")

    except Exception as e:
        logger.error(f"[{job_id}] Pipeline failed: {e}", exc_info=True)
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = str(e)


async def discover_podcasts(keyword: str) -> list[dict]:
    """
    Use iTunes Search API to find podcasts matching a keyword.
    Free, no API key required.
    """
    import httpx
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://itunes.apple.com/search",
                params={"term": keyword, "media": "podcast", "limit": 10, "entity": "podcast"}
            )
            data = resp.json()
            results = data.get("results", [])
            podcasts = []
            for r in results:
                feed_url = r.get("feedUrl")
                name = r.get("collectionName", "Unknown")
                if feed_url:
                    podcasts.append({
                        "name": name,
                        "rss": feed_url,
                        "icp_notes": f"Podcast about {keyword}",
                    })
            logger.info(f"Discovered {len(podcasts)} podcasts for keyword '{keyword}'")
            return podcasts
    except Exception as e:
        logger.error(f"Podcast discovery failed: {e}")
        return []


# ─── Serve React frontend ─────────────────────────────────────────────────────

UI_DIST = Path(__file__).parent.parent / "ui" / "dist"

if UI_DIST.exists():
    assets_dir = UI_DIST / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        index = UI_DIST / "index.html"
        if index.exists():
            return FileResponse(str(index))
        return {"error": "Frontend not built"}
