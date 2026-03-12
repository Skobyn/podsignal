# PodSignal v2 — Web App Plan

## What Was Built
Transformed the CLI pipeline into a full web application.

### Architecture
- **Backend:** FastAPI (api/main.py) — REST API wrapping the existing pipeline
- **Geocoder:** Nominatim-based (api/geocoder.py) — extracts location hints from guest data, geocodes to lat/lng
- **Pipeline adapter:** Async wrapper (api/pipeline.py) — runs existing podsignal pipeline in thread pool
- **Frontend:** Vanilla HTML/JS + Leaflet.js (ui/dist/index.html) — geographic map UI with guest detail panel
- **Container:** Docker (Dockerfile)
- **CI/CD:** GitHub Actions → GCP Cloud Run (deploy on push to main)

### Features
- Keyword search → iTunes API discovers relevant podcasts automatically
- OR provide RSS feeds directly
- Background job execution with progress polling
- Geographic map with color-coded pins (green=high fit, purple=medium, orange=low)
- Click pin → popup → full guest detail panel
- Guest detail: name, company, title, episode, topics, key insight, location, outreach email, pitch reasoning
- LinkedIn button if profile found
- Cached guests persist across searches
- Auth scaffold present (disabled) — ready to enable Firebase Auth

## Deployment
- GitHub Actions CI/CD configured
- Pushes to main auto-deploy to Cloud Run
- GCP_SA_KEY secret set
- ANTHROPIC_API_KEY needed (set manually in GitHub repo secrets)

## Missing / Known Gaps
- ANTHROPIC_API_KEY not in secrets yet (needed for guest extraction + outreach generation)
- Location extraction relies on heuristics — geocoding hit rate ~60-70%
- SerpAPI not configured (LinkedIn search uses Google heuristic)
- Auth disabled (Firebase Auth scaffolded but not implemented)
