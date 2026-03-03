# 🎙️ PodSignal

**Podcast guest intelligence pipeline — find warm B2B leads from public RSS feeds, personalize outreach with their own words.**

PodSignal monitors podcasts your ICP appears on, extracts guest names and talking points from episode descriptions, finds their LinkedIn profiles, and uses Claude to draft outreach emails that reference what they *specifically* said on the show.

**"I heard your episode on [Podcast] where you talked about [specific thing]" converts at 3-4x a generic cold email.**

**Total cost per lead: ~$0.004 (Claude API only. All data is free.)**

---

## Why Podcast Guests Are The Perfect Lead

People who go on podcasts have self-selected as:

- **Budget authority** — founders, VPs, and C-suite go on podcasts. ICs don't.
- **Brand builders** — they're actively investing in visibility, which signals growth mindset
- **Problem-aware** — they talked about a specific challenge on air, in their own words
- **Warm to outreach** — someone who just published an episode is in "public mode"

And because they said it on a podcast, you have a legitimate, non-creepy reason to reference it: *you listened.*

---

## How It Works

```
podcasts.yaml (your list of target shows)
        ↓
RSS Feed Fetcher
[pulls all episodes, last N days]
        ↓
Claude Guest Extractor
[parses titles + descriptions → guest name, company, topics, key insights]
        ↓
LinkedIn Finder
[Google search: "name company site:linkedin.com/in"]
        ↓
Claude Synthesizer
[scores fit + drafts personalized outreach grounded in episode content]
        ↓
Output: CSV / JSON
[ready for HubSpot, Airtable, or direct outreach]
```

---

## Quickstart

### 1. Clone the repo

```bash
git clone https://github.com/yourusername/podsignal.git
cd podsignal
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Set your API key

```bash
cp .env.example .env
```

Edit `.env`:
```
ANTHROPIC_API_KEY=your_key_here
```

No other API keys needed. All podcast data comes from public RSS feeds. LinkedIn discovery uses Google search (no API key required).

### 4. Add your target podcasts

Edit `podcasts.yaml` with shows your ICP appears on:

```yaml
podcasts:
  - name: "How I Built This"
    rss: "https://feeds.npr.org/510313/podcast.xml"
    icp_notes: "Founders who scaled consumer businesses"

  - name: "My First Million"
    rss: "https://feeds.megaphone.fm/mfm"
    icp_notes: "Entrepreneurs actively building new revenue streams"
```

Finding RSS feeds: Google `"[podcast name] RSS feed"` or paste the show URL into [Podcast Index](https://podcastindex.org).

### 5. Configure your ICP

Edit `config.yaml`:

```yaml
your_company:
  name: "Acme Analytics"
  description: "Revenue intelligence for B2B SaaS founders"
  pitch: "We help founders see what's actually driving growth before their next board meeting"

search:
  days_back: 30         # How far back to scan for episodes
  max_episodes_per_show: 20

output:
  min_score: 6
  format: "csv"
```

### 6. Run it

```bash
python -m podsignal.main
```

---

## Output Fields

| Field | Description |
|---|---|
| `guest_name` | Extracted guest name |
| `guest_company` | Their company at time of episode |
| `guest_title` | Their title if mentioned |
| `podcast_name` | Show they appeared on |
| `episode_title` | Full episode title |
| `episode_date` | Air date |
| `episode_url` | Link to the episode |
| `key_topics` | Topics they discussed (3-5 bullets) |
| `key_insight` | Most quotable/specific thing they said |
| `linkedin_url` | Their LinkedIn profile (Google-found) |
| `prospect_score` | Claude's fit score for your ICP (1-10) |
| `pain_point` | Inferred pain point from what they discussed |
| `outreach_trigger` | The specific episode moment to reference |
| `email_subject` | Personalized subject line |
| `email_body` | Full email draft referencing the episode |
| `reasoning` | Why Claude scored them this way |

---

## Finding RSS Feeds for Your Niche

Some starting points by vertical:

**Restaurant / Hospitality**
- Restaurant Unstoppable: `https://feeds.buzzsprout.com/...`
- Hospitality Daily: `https://feeds.buzzsprout.com/...`
- The Restaurant Coach: public RSS on Spotify/Apple

**B2B SaaS**
- SaaStr Podcast, Lenny's Podcast, The SaaS Podcast, Founders, My First Million

**E-commerce / Retail**
- Shopify Masters, 2X eCommerce, Retail Remix

**General Founder/Operator**
- How I Built This, Masters of Scale, Acquired, 20VC, The Tim Ferriss Show

Tip: Focus on shows where guests are operating businesses at your target size. A guest on a 10-person founder podcast has different budget authority than a guest on a Fortune 500 leadership show.

---

## Rate Limits & Costs

| Component | Cost | Limit |
|---|---|---|
| RSS Feeds | $0 | No limit — it's just HTTP |
| Claude API (per episode) | ~$0.002 | Depends on your tier |
| Google Search (LinkedIn) | $0 | ~100 searches before CAPTCHA |
| **100 leads/month** | **~$0.40** | |
| **1,000 leads/month** | **~$4.00** | |

Google search throttle: PodSignal adds a 2-second delay between searches. If you're running large volumes, consider the SerpAPI free tier (100 searches/month free) as a drop-in replacement — see `config.yaml`.

---

## Project Structure

```
podsignal/
├── podsignal/
│   ├── __init__.py
│   ├── main.py              # Orchestrator
│   ├── rss_fetcher.py       # RSS feed parser
│   ├── guest_extractor.py   # Claude: extract guests from episode data
│   ├── linkedin_finder.py   # Google search → LinkedIn URL
│   ├── synthesizer.py       # Claude: score + draft personalized email
│   └── output_handler.py    # CSV / JSON export
├── podcasts.yaml            # Your target shows (edit this)
├── config.yaml              # Your ICP + search settings (edit this)
├── .env.example
├── requirements.txt
├── LICENSE
└── README.md
```

---

## Contributing

PRs welcome. Priority areas:

- [ ] Apple Podcasts / Spotify scraper for show discovery
- [ ] Transcript support via Whisper API (richer guest intel)
- [ ] Email finder chaining (Hunter → Apollo → pattern guess)
- [ ] CRM push integrations (HubSpot, Airtable, Notion)
- [ ] Slack alerts for high-score guests in real time
- [ ] Deduplication across runs (don't re-process guests you've already seen)

---

## License

MIT — free to use, modify, and commercialize. Attribution appreciated but not required.

---

*Built with public RSS feeds and Claude. No paid data vendors.*
