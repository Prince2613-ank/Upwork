# Flodata Analytics: Upwork Market-Intelligence Data Collection System

**Local database:** all dates are now saved as rows in `output/database.db`, with collection runs recorded separately. Existing daily files are merged without deletion. See [local storage and migration](docs/LOCAL_DATABASE.md).

**Linux server deployment:** use the new [server pipeline guide](docs/SERVER_DEPLOYMENT.md) for the authenticated dashboard, persistent browser sessions, two workers at 5–7 jobs/minute each, daily scheduling, PostgreSQL storage, Google Chat HTML delivery, Docker Compose, and GitHub release/deployment workflows. The existing local CLI below remains available. Scheduling and outbound delivery are disabled until configured.

An enterprise-grade, structured market-intelligence collection engine designed to harvest and normalize Upwork job postings, client purchasing patterns, and complete feedback history over a rolling **one-month window** for downstream B2B analysis with Claude.

---

## 1. What the Project Does

The system collects Upwork job listings, comprehensive client spending and hiring profiles, and complete historical contract feedback for companies operating across targeted geographical jurisdictions.

Rather than merely scraping job listings, it ensures **data completeness** across nested objects:
- **Full, untruncated job descriptions** (satisfying the explicit requirement *"Description पूरी चाहिए"*).
- **Comprehensive "About the Client" profiles** (total spend, hire rate, active jobs, member tenure, rating, location).
- **Client Recent History** (every past completed contract, previous job titles, amounts, and dates).
- **100% Un-truncated Review Text** (actively clicking and inspecting expansion controls to eliminate `... More` cutoffs).

---

## 2. Business Purpose

The dataset collected by this engine serves four strategic goals for **Flodata Analytics**:
1. **Identify Outsourcing Companies**: Discover which businesses actively hire external talent.
2. **Analyze Work Domains**: Determine exact scopes and deliverables being outsourced.
3. **Map Technology Stacks**: Track technologies, libraries, and frameworks clients repeatedly purchase.
4. **Surface High-Value Leads**: Generate high-confidence business development intelligence for outbound outreach.

Downstream, the canonical JSON dataset is delivered directly to Claude for automated intelligence synthesis.

---

## 3. Architecture

```
flodata-upwork-intelligence/
├── config.py                 # Target locations, search params, date cutoff window
├── main.py                   # Unified CLI entrypoint (--poc, --test-50, --full, --resume)
├── models/
│   └── schema.py             # Pydantic data contracts (JobPosting, ClientInfo, History, Checkpoint)
├── sources/
│   ├── base.py               # Abstract BaseDataSource interface
│   ├── mock_source.py        # High-fidelity fixture engine for offline tests & validation
│   ├── browser_source.py     # Playwright supervised browser source connecting via Chrome CDP
│   └── api_source.py         # Official Upwork GraphQL API adapter & capability documentation
├── parsers/
│   ├── job_parser.py         # Extracts complete job metadata, budget, skills, full description
│   ├── client_parser.py      # Extracts About Client fields (spend, rating, hire rate)
│   ├── history_parser.py     # Parses client recent history contract cards
│   ├── review_extractor.py   # Resolves full un-truncated review text
│   ├── truncation_detector.py# Audits reviews for trailing ellipses or clipping
│   └── date_parser.py        # Date-cutoff parser and stopping engine
├── pipeline/
│   ├── collector.py          # Paginated collection orchestrator with date-cutoff stop
│   ├── deduplicator.py       # Deduplication engine tracking seen job IDs
│   ├── checkpoint.py         # Atomic checkpoint persistence for safe resumability
│   ├── normalizer.py         # Schema compliance & string normalization
│   ├── validator.py          # Generates authoritative run audit reports
│   └── exporter.py           # Exports Claude-ready JSON & convenience CSV
├── tests/                    # 10 comprehensive test suites (22 unit tests)
├── data/
│   ├── raw/                  # Timestamped raw snapshots (Requirement 8)
│   ├── processed/            # Normalized JSON data batches
│   ├── checkpoints/          # Atomic run state checkpoints
│   └── exports/              # Claude-ready canonical outputs (JSON & CSV)
├── .env.example              # Environment variable template
└── .gitignore                # Protects secrets, browser profiles, and temporary caches
```

---

## 4. Required Credentials & Access

The system operates across three modes:

| Mode | Required Credentials / Access |
|---|---|
| **Mock (`mock`)** | None. Completely self-contained offline dataset of 65+ jobs across 2 pages with date-spaced cutoffs. |
| **Browser CDP (`browser`)** | An active, authenticated Chrome session launched with `--remote-debugging-port=9222`. The user is legitimately logged into Upwork in their browser. No credential scraping or CAPTCHA bypass is attempted. |
| **Official API (`api`)** | Approved Upwork OAuth2 developer credentials (`UPWORK_ACCESS_TOKEN` or `UPWORK_CLIENT_ID` / `SECRET`). |

---

## 5. Official API vs. Browser Access Method Analysis

In compliance with **Requirement 1 & 6**, an audit of Upwork's official developer documentation (`https://api.upwork.com/graphql`) was conducted:

| Field | Official GraphQL API | UI / Browser DOM |
|---|---|---|
| `job_id`, `title`, `description` | Available (`marketplaceJobPostingsSearch`) | Available |
| `budget`, `skills`, `category` | Available (`contractTerms`, `annotations`) | Available |
| `client location` | Partial (Country code only) | Full (Country + City) |
| `payment_verified` | Available | Available |
| `client total spend` | Restricted / Coarse bucket | Full (`$X total spent`) |
| `hire_rate`, `active_hires` | Unavailable in public search | Available |
| `client_recent_history` | **UNAVAILABLE** across 3rd parties | **Available** |
| `complete review / feedback` | **UNAVAILABLE** across 3rd parties | **Available** |

*Reason*: In Upwork's GraphQL schema, historical contract feedback is scoped to `contract(id: $id) { feedback { ... } }`, which strictly requires that the authenticated user be a direct contractual party. You cannot query arbitrary client contract histories across third-party freelancers. Therefore, the browser-assisted supervised workflow is required to capture full client history.

---

## 6. Environment Variables (`.env`)

Copy `.env.example` to `.env` and configure:

```ini
# Data Source Mode: "mock", "browser", or "api"
DATA_SOURCE_MODE=mock

# Playwright / Chrome CDP Settings (for browser mode)
CHROME_CDP_URL=http://localhost:9222
BROWSER_HEADLESS=false

# Date Window (in days for cutoff calculation; default: 30 days = 1 month)
DATE_WINDOW_DAYS=30

# Request Pacing & Safety Settings (seconds)
MIN_REQUEST_DELAY_SEC=2.0
MAX_REQUEST_DELAY_SEC=4.0
MAX_RETRIES=3
BACKOFF_FACTOR=2.0
```

---

## 7. Installation

Python 3.10+ is required. All necessary packages are installed:

```bash
pip install playwright beautifulsoup4 pydantic python-dateutil python-dotenv pytest
python -m playwright install chromium
```

---

## 8. Running the 5-Job Proof of Concept (POC)

To run the initial 5-job POC:

```bash
python main.py --poc
```

---

## 9. Running the 50-Job Test

To run the 50-job multi-page verification test:

```bash
python main.py --test-50
```

---

## 10. Running the Full One-Month Collection

To collect the complete set of jobs spanning the most recent one month (stopping automatically once jobs exceed the 30-day cutoff):

```bash
python main.py --full
```

You can customize the date window (e.g. 45 days):

```bash
python main.py --full --days 45
```

---

## 11. Output Format

### Canonical JSON: `data/exports/upwork_last_month.json`

```json
{
  "job_id": "~01mock0000abcdef",
  "job_url": "https://www.upwork.com/jobs/~01mock0000abcdef",
  "title": "Dutch -> English Comic Translation & Manual Lettering - 20 Pages [Batch 1]",
  "posted_at": "2026-09-20T13:30:00+00:00",
  "posted_raw": "Posted 1 hour ago",
  "description": "Full un-truncated multi-paragraph job description...",
  "budget": {
    "type": "fixed-price",
    "amount": 25.0,
    "currency": "USD",
    "raw_text": "$25.00 fixed-price"
  },
  "experience_level": "Intermediate",
  "duration": "1 to 3 months",
  "skills": ["Dutch to English Translation", "Adobe Illustrator", "Lettering"],
  "about_client_raw": "Payment method verified\n5.0 of 5 stars (18 reviews)\n...",
  "client": {
    "location": "Netherlands",
    "payment_verified": true,
    "rating": 5.0,
    "reviews_count": 18,
    "total_spent": "$3.5K+ spent",
    "total_spent_amount": 3500.0,
    "jobs_posted": 28,
    "hire_rate": 75.0,
    "member_since": "Jan 15, 2021"
  },
  "client_recent_history": [
    {
      "job_title": "Past Milestone Assignment #1",
      "date": "May 2024 - Jun 2024",
      "rating": 5.0,
      "amount": "$250.00",
      "freelancer": "Developer_0_0",
      "full_review": "Flodata and their engineering team did an extraordinary job...",
      "is_truncated": false
    }
  ],
  "source": {
    "collected_at": "2026-09-20T14:40:00Z",
    "source_type": "mock",
    "search_page": 1
  }
}
```

### Convenience CSV: `data/exports/upwork_last_month.csv`

Flattened CSV containing high-level client metrics, review counts, and review summaries for quick tabular preview.

---

## 12. Validation Report

Every collection run outputs an authoritative audit report:

```markdown
## COLLECTION VALIDATION

Jobs collected: 56
Duplicate jobs: 0
Full descriptions: 56/56
About Client: 56/56
Recent history: 56/56
Complete reviews: 168/168
Suspected truncated reviews: 0
Oldest job: 2026-08-21T12:30:00+00:00
Newest job: 2026-09-20T13:30:00+00:00
Pages: 2
Errors: 0
Retries: 0
Rate-limit responses: 0
```

To re-run validation on previously collected files at any time:

```bash
python main.py --validate
```

---

## 13. Known Limitations & Transparency

1. **Official Upwork API**: Client historical feedback across third-party freelancers is not accessible via public GraphQL search queries.
2. **Browser Authentication**: Upwork requires an active user session to view search listings and job drawers. Running with `DATA_SOURCE_MODE=browser` requires connecting to an already authenticated Chrome session.
3. **Client Privacy**: Clients with 0 previous jobs will have an empty `client_recent_history` array. The validator reports `recent_history_ratio` accurately without pretending missing records exist.

---

## 14. How to Resume an Interrupted Run

The system records atomic checkpoints after every search page in `data/checkpoints/checkpoint_latest.json`.

If a run is terminated or interrupted, execute:

```bash
python main.py --resume
```

The collector will load the latest checkpoint, restore the list of previously collected job IDs to avoid duplicate requests, and resume pagination directly from `last_page + 1`.
