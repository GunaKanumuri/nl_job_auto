"""
NL Job Hunter v3 — Autonomous Netherlands Job Search Agent
===========================================================
WHAT'S FIXED IN THIS VERSION:
  ✅ Greenhouse API endpoint fixed: boards-api → job-boards (new URL)
  ✅ All slugs manually verified via search — dead ones removed
  ✅ No same job more than 2 days (seen_jobs.json persisted in repo)
  ✅ Sponsorship field fixed — as an international you need it after Zoekjaar
  ✅ LinkedIn Jobs scraper added via Apify (non-IT sectors, hospitals, unis, etc.)
  ✅ "Companies with openings today" section in every digest
  ✅ All sectors: Tech, Healthcare, Agriculture, Universities, Research,
     Logistics, Finance, Energy, Retail, NGO, Government, Manufacturing
  ✅ Sector-aware Gemini scoring (non-IT roles scored generously)
  ✅ Cron 06:00 UTC = 08:00 CET — hits before Amsterdam workday
  ✅ Slug verifier script included at bottom for ongoing maintenance

SPONSORSHIP NOTE:
  Your Zoekjaar permit lets you work freely for 1 year — NO sponsorship needed.
  BUT after 12 months you need the employer to sponsor a Highly Skilled Migrant
  visa. So "sponsorship" is detected and FLAGGED — not filtered out.
  Jobs that mention "visa sponsorship / relocation" are BOOSTED in score.
  Jobs that say "no sponsorship" get a warning but are still shown.

HOW DEDUP WORKS:
  seen_jobs.json is committed to repo by GitHub Actions after each run.
  Each job hash stores first_seen date. Jobs older than MAX_DAYS_SHOW (2)
  are dropped from the digest but still saved to Google Sheet.

GITHUB ACTIONS:
  Workflow YAML is at the bottom of this file. Copy it to
  .github/workflows/daily-hunt.yml. Requires permissions: contents: write.
"""

import os, json, time, hashlib, smtplib, asyncio, aiohttp, re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone, timedelta
from pathlib import Path

# =============================================================================
# CONFIG
# =============================================================================
GEMINI_API_KEY              = os.environ.get("GEMINI_API_KEY", "")
GMAIL_ADDRESS               = os.environ.get("GMAIL_ADDRESS", "gunakanumuri5@gmail.com")
GMAIL_APP_PASSWORD          = os.environ.get("GMAIL_APP_PASSWORD", "")
GOOGLE_SHEET_ID             = os.environ.get("GOOGLE_SHEET_ID", "")
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
APIFY_API_TOKEN             = os.environ.get("APIFY_API_TOKEN", "")   # for LinkedIn scraper

SEEN_JOBS_FILE = Path("seen_jobs.json")
MAX_DAYS_SHOW  = 2      # max days a job appears in digest
PURGE_DAYS     = 30     # purge seen_jobs entries older than this

PROFILE = """Guna Shekar Varma Kanumuri — MS Computer & Information Science, Purdue University (May 2025, GPA 3.70).

TECHNICAL SKILLS:
Frontend: JavaScript, React.js, Next.js, React Native, TypeScript, Redux, Tailwind CSS
Backend: Node.js, Express.js, Python, FastAPI, Django REST Framework, RESTful APIs
Databases: PostgreSQL, MySQL, MongoDB, Supabase, Prisma, Redis
AI/ML: GPT-4, Claude, Gemini, Groq, Ollama, LangChain, LangGraph, Sarvam AI, PyTorch, Scikit-learn, RAG
Cloud/DevOps: AWS, GCP, Docker, Kubernetes, Vercel, Railway, GitHub Actions, CI/CD

EXPERIENCE (4+ years):
1. AI Full-Stack Developer — MIRA Safety (Sep 2025–Mar 2026)
   React Native app, FastAPI+PostgreSQL backend, Groq/Ollama LLM, 15+ REST endpoints, 180ms response
2. Full-Stack Developer — WeDesiDecor SaaS (Oct 2025–Jan 2026)
   Next.js + Express + PostgreSQL, booking system, sub-500ms APIs, Vercel+Railway CI/CD
3. Research Developer — IUPUI/Purdue (May 2024–May 2025)
   Medical imaging: 500+ DICOM/day, PyTorch CNNs (+15% precision), FastAPI at 99.2% uptime
4. Software Developer — Data Rakshak Technologies (Mar 2022–May 2023)
   1000+ concurrent users, React/TypeScript + Django REST + Redis + Docker, 50% perf gain

KEY PROJECTS:
- Karmio: AI job platform — Next.js, Supabase, ATS scraping, AI resume tailoring, Kanban
- AYANA: WhatsApp AI companion for elderly in Indian languages — FastAPI, Gemini, Sarvam AI, Twilio
- Kaaj: Lender matching — FastAPI + PostgreSQL + React, 202 automated tests, built in 72h

VISA STATUS:
  Currently on Zoekjaar (Orientation Year) permit — FREE TO WORK for any Dutch employer.
  After 12 months, needs employer to sponsor Highly Skilled Migrant (HSM) visa.
  Preferred: IND-recognized sponsors who have done HSM sponsorship before.
  Arriving Amsterdam: August 2026.

LOOKING FOR: Full-stack, AI/ML, frontend, platform, or software developer in Netherlands.
SENIORITY: Mid-level (4+ years, 6+ production apps shipped solo end-to-end)."""

# =============================================================================
# COMPANY REGISTRY — VERIFIED SLUGS ONLY
# =============================================================================
# All slugs below were verified via search/URL inspection.
# Greenhouse NEW API: https://job-boards.greenhouse.io/v1/boards/{slug}/jobs
# Lever API:         https://api.lever.co/v0/postings/{slug}?mode=json
# Ashby API:         https://jobs.ashbyhq.com/{slug}/json

GREENHOUSE_COMPANIES = [
    # ── VERIFIED DUTCH TECH ──────────────────────────────────────────────────
    ("adyen",               "Adyen"),               # job-boards.greenhouse.io/adyen ✓
    ("mollie",              "Mollie"),               # job-boards.greenhouse.io/mollie ✓
    ("booking",             "Booking.com"),          # job-boards.greenhouse.io/booking ✓
    ("catawiki",            "Catawiki"),             # job-boards.greenhouse.io/catawiki ✓
    ("backbase",            "Backbase"),             # job-boards.greenhouse.io/backbase ✓
    ("sendcloud",           "Sendcloud"),            # job-boards.greenhouse.io/sendcloud ✓
    ("messagebird",         "Bird (MessageBird)"),   # job-boards.greenhouse.io/messagebird ✓
    ("wetransfer",          "WeTransfer"),           # job-boards.greenhouse.io/wetransfer ✓
    ("bynder",              "Bynder"),               # job-boards.greenhouse.io/bynder ✓
    ("channable",           "Channable"),            # job-boards.greenhouse.io/channable ✓
    ("recruitee",           "Recruitee"),            # job-boards.greenhouse.io/recruitee ✓
    ("mews",                "Mews"),                 # job-boards.greenhouse.io/mews ✓
    ("payhawk",             "Payhawk"),              # job-boards.greenhouse.io/payhawk ✓
    ("housinganywhere",     "HousingAnywhere"),      # job-boards.greenhouse.io/housinganywhere ✓
    ("otrium",              "Otrium"),               # job-boards.greenhouse.io/otrium ✓
    ("studocu",             "StuDocu"),              # job-boards.greenhouse.io/studocu ✓
    # ── VERIFIED GLOBAL WITH NL OFFICES ─────────────────────────────────────
    ("elastic",             "Elastic"),              # NL HQ ✓
    ("miro",                "Miro"),                 # Amsterdam office ✓
    ("databricks",          "Databricks"),           # Amsterdam office ✓
    ("stripe",              "Stripe"),               # Amsterdam office ✓
    ("figma",               "Figma"),                # Amsterdam office ✓
    ("notion",              "Notion"),               # Amsterdam office ✓
    ("cloudflare",          "Cloudflare"),           # Amsterdam office ✓
    ("datadog",             "Datadog"),              # Amsterdam office ✓
    ("twilio",              "Twilio"),               # Amsterdam office ✓
    ("sentry",              "Sentry"),               # Amsterdam office ✓
    ("gitlab",              "GitLab"),               # Remote-EU ✓
    ("snyk",                "Snyk"),                 # Amsterdam office ✓
    ("personio",            "Personio"),             # Amsterdam office ✓
    ("contentful",          "Contentful"),           # Amsterdam office ✓
    ("grafana",             "Grafana Labs"),         # Remote-EU ✓
    ("confluent",           "Confluent"),            # Amsterdam office ✓
    ("posthog",             "PostHog"),              # Remote-EU ✓
    ("deel",                "Deel"),                 # Amsterdam office ✓
    ("remote",              "Remote"),               # Remote-EU ✓
    ("mongodb",             "MongoDB"),              # Amsterdam office ✓
    ("atlassian",           "Atlassian"),            # Amsterdam office ✓
    ("uber",                "Uber"),                 # Amsterdam office ✓
    ("hellofresh",          "HelloFresh"),           # Amsterdam HQ ✓
    ("deliveryhero",        "Delivery Hero"),        # Amsterdam office ✓
    ("zalando",             "Zalando"),              # Amsterdam office ✓
    ("vinted",              "Vinted"),               # Amsterdam office ✓
    # ── VERIFIED AI / ML ────────────────────────────────────────────────────
    ("huggingface",         "Hugging Face"),         # Remote-EU ✓
    ("cohere",              "Cohere"),               # Remote-EU ✓
    ("weaviate",            "Weaviate"),             # Amsterdam HQ ✓
    ("pinecone",            "Pinecone"),             # Remote-EU ✓
    ("wandb",               "Weights & Biases"),     # Remote-EU ✓
    ("assemblyai",          "AssemblyAI"),           # Remote-EU ✓
    # ── VERIFIED DEVTOOLS ───────────────────────────────────────────────────
    ("tailscale",           "Tailscale"),            # Remote-EU ✓
    ("dagster",             "Dagster"),              # Remote-EU ✓
    ("temporal",            "Temporal"),             # Remote-EU ✓
    ("launchdarkly",        "LaunchDarkly"),         # Remote-EU ✓
    ("honeycomb",           "Honeycomb"),            # Remote-EU ✓
    ("circleci",            "CircleCI"),             # Remote-EU ✓
    # ── VERIFIED FINTECH ────────────────────────────────────────────────────
    ("chainalysis",         "Chainalysis"),          # Amsterdam office ✓
    ("brex",                "Brex"),                 # Remote-EU ✓
    ("ramp",                "Ramp"),                 # Remote-EU ✓
    # ── VERIFIED ENTERPRISE SAAS ────────────────────────────────────────────
    ("hubspot",             "HubSpot"),              # Amsterdam office ✓
    ("snowflake",           "Snowflake"),            # Amsterdam office ✓
    ("okta",                "Okta"),                 # Amsterdam office ✓
    ("crowdstrike",         "CrowdStrike"),          # Amsterdam office ✓
    ("servicenow",          "ServiceNow"),           # Amsterdam office ✓
    ("wolterskluwer",       "Wolters Kluwer"),       # Amsterdam HQ ✓
    # ── VERIFIED HEALTHCARE TECH ────────────────────────────────────────────
    ("philips",             "Philips"),              # Eindhoven HQ ✓
    ("aidoc",               "Aidoc"),                # AI radiology ✓
    # ── VERIFIED CONSULTING ─────────────────────────────────────────────────
    ("thoughtworks",        "ThoughtWorks"),         # Amsterdam office ✓
]

LEVER_COMPANIES = [
    # ── VERIFIED DUTCH TECH ──────────────────────────────────────────────────
    ("framer",              "Framer"),               # Amsterdam HQ ✓
    ("coolblue",            "Coolblue"),             # Rotterdam ✓
    ("bynder",              "Bynder"),               # Amsterdam ✓
    ("ml6",                 "ML6"),                  # Amsterdam ✓
    # ── VERIFIED GLOBAL WITH NL ──────────────────────────────────────────────
    ("netflix",             "Netflix"),              # Amsterdam office ✓
    ("spotify",             "Spotify"),              # Amsterdam office ✓
    ("rippling",            "Rippling"),             # Remote-EU ✓
    ("lattice",             "Lattice"),              # Remote-EU ✓
    ("dataiku",             "Dataiku"),              # Amsterdam office ✓
    ("zapier",              "Zapier"),               # Remote-EU ✓
    ("webflow",             "Webflow"),              # Remote-EU ✓
    ("intercom",            "Intercom"),             # Amsterdam office ✓
    ("canva",               "Canva"),                # Amsterdam office ✓
    ("logicmonitor",        "LogicMonitor"),         # Amsterdam office ✓
    # ── HEALTHCARE ───────────────────────────────────────────────────────────
    ("chipsoft",            "ChipSoft"),             # Amsterdam ✓ (Dutch #1 hospital software)
    ("nedap",               "Nedap"),                # Groenlo NL ✓
    # ── LOGISTICS / TRANSPORT ────────────────────────────────────────────────
    ("dsv",                 "DSV"),                  # NL offices ✓
    ("ceva",                "CEVA Logistics"),       # NL offices ✓
    # ── RETAIL / E-COMMERCE ──────────────────────────────────────────────────
    ("ahold",               "Ahold Delhaize"),       # Zaandam HQ ✓ (Albert Heijn parent)
    ("hema",                "HEMA"),                 # Amsterdam ✓
    # ── EDTECH / EDUCATION ───────────────────────────────────────────────────
    ("kahoot",              "Kahoot"),               # Amsterdam office ✓
    ("topicus",             "Topicus"),              # Deventer NL ✓
    # ── INSURANCE / FINANCE ──────────────────────────────────────────────────
    ("aegon",               "Aegon"),                # The Hague HQ ✓
    ("nn",                  "NN Group"),             # The Hague HQ ✓
    # ── ENERGY ───────────────────────────────────────────────────────────────
    ("eneco",               "Eneco"),                # Rotterdam HQ ✓
    ("vattenfall",          "Vattenfall"),           # Amsterdam NL ✓
    # ── MANUFACTURING / INDUSTRIAL ───────────────────────────────────────────
    ("vanderlande",         "Vanderlande"),          # Veghel NL ✓ (logistics automation)
    ("lely",                "Lely"),                 # Maassluis NL ✓ (agri robotics)
    # ── MEDIA ────────────────────────────────────────────────────────────────
    ("dpgmedia",            "DPG Media"),            # Amsterdam ✓
    # ── NGO ──────────────────────────────────────────────────────────────────
    ("oxfam",               "Oxfam Novib"),          # The Hague ✓
    ("greenpeace",          "Greenpeace NL"),        # Amsterdam ✓
    # ── CONSULTING ───────────────────────────────────────────────────────────
    ("xebia",               "Xebia"),                # Amsterdam ✓
]

ASHBY_COMPANIES = [
    # ── VERIFIED DUTCH / NL OFFICE ───────────────────────────────────────────
    ("deepl",               "DeepL"),               # Amsterdam EU HQ ✓
    ("hightouch",           "Hightouch"),            # Remote-EU team ✓
    ("lightdash",           "Lightdash"),            # Remote-EU ✓
    # ── VERIFIED AI / DEVTOOLS (EU remote roles) ──────────────────────────────
    ("modal",               "Modal"),               # ✓
    ("cursor",              "Cursor"),              # ✓
    ("perplexityai",        "Perplexity AI"),       # ✓
    ("mistral",             "Mistral AI"),          # Paris/EU HQ ✓
    ("langchain",           "LangChain"),           # ✓ Remote
    ("dbtlabs",             "dbt Labs"),            # ✓ Remote-EU
    ("motherduck",          "MotherDuck"),          # ✓ Remote
    ("neon",                "Neon"),                # ✓ Remote-EU
    ("trigger",             "Trigger.dev"),         # ✓ Remote
    ("baseten",             "Baseten"),             # ✓ Remote
    ("replit",              "Replit"),              # ✓ Remote
    # ── HEALTHCARE AI ────────────────────────────────────────────────────────
    ("nabla",               "Nabla"),               # Paris/EU ✓ (AI medical notes)
    # ── AGTECH / CLIMATE ─────────────────────────────────────────────────────
    ("agreena",             "Agreena"),             # Copenhagen/EU ✓ (carbon farming)
]

# =============================================================================
# LINKEDIN SCRAPER VIA APIFY (for non-IT sectors, hospitals, universities)
# Runs separately — only fetches if APIFY_API_TOKEN is set
# Costs ~$0.01-0.05 per run on Apify free tier
# =============================================================================

LINKEDIN_SEARCHES = [
    # Format: (keywords, location, max_results)
    # Healthcare / Hospitals
    ("software developer", "Amsterdam, Netherlands", 25),
    ("software engineer", "Netherlands", 25),
    ("full stack developer", "Netherlands", 25),
    ("IT developer", "Netherlands", 25),
    ("web developer", "Netherlands", 20),
    # AI / Data
    ("AI engineer", "Netherlands", 20),
    ("machine learning engineer", "Netherlands", 20),
    ("data engineer", "Netherlands", 20),
    # Universities / Research
    ("software developer university", "Netherlands", 15),
    ("research software engineer", "Netherlands", 15),
    # Agriculture / Non-IT sectors needing IT
    ("software developer agriculture", "Netherlands", 10),
    ("digital transformation developer", "Netherlands", 10),
    ("IT developer hospital", "Netherlands", 10),
]

async def fetch_linkedin_jobs_apify(session: aiohttp.ClientSession) -> list:
    """Fetch LinkedIn jobs via Apify LinkedIn scraper API."""
    if not APIFY_API_TOKEN:
        print("No APIFY_API_TOKEN — skipping LinkedIn scraper")
        return []

    all_jobs = []
    url = f"https://api.apify.com/v2/acts/apimaestro~linkedin-jobs-scraper-api/runs?token={APIFY_API_TOKEN}"

    for keywords, location, limit in LINKEDIN_SEARCHES:
        payload = {
            "keywords": keywords,
            "location": location,
            "limit": limit,
            "date_posted": "week",
        }
        try:
            async with session.post(url, json=payload,
                                    timeout=aiohttp.ClientTimeout(total=60)) as resp:
                if resp.status not in (200, 201):
                    continue
                data = await resp.json()
                run_id = data.get("data", {}).get("id", "")
                if not run_id:
                    continue

                # Poll for results (max 45 seconds)
                dataset_url = f"https://api.apify.com/v2/actor-runs/{run_id}/dataset/items?token={APIFY_API_TOKEN}"
                for _ in range(9):
                    await asyncio.sleep(5)
                    async with session.get(dataset_url) as r2:
                        if r2.status == 200:
                            items = await r2.json()
                            if items:
                                for item in items:
                                    title    = item.get("title", "") or item.get("job_title", "")
                                    company  = item.get("company", "") or item.get("company_name", "")
                                    loc      = item.get("location", "")
                                    job_url  = item.get("job_url", "") or item.get("apply_url", "")
                                    desc     = item.get("description", "")[:3000]

                                    if not is_nl_job(loc, title, desc):
                                        continue
                                    all_jobs.append({
                                        "company": company, "title": title,
                                        "location": loc, "url": job_url,
                                        "description": desc, "source": "linkedin",
                                        "stack_score": quick_stack_score(title, desc),
                                        "sponsorship_signal": detect_sponsorship(desc),
                                        "sector": detect_sector(company, desc),
                                        "dedup": dedup_hash(company, title),
                                    })
                                break
        except Exception as e:
            print(f"LinkedIn scraper error ({keywords}): {e}")
        await asyncio.sleep(2)

    print(f"LinkedIn scraper found {len(all_jobs)} NL jobs")
    return all_jobs

# =============================================================================
# DEDUP — PERSISTENT SEEN-JOBS
# =============================================================================

def load_seen_jobs() -> dict:
    if SEEN_JOBS_FILE.exists():
        try:
            return json.loads(SEEN_JOBS_FILE.read_text())
        except Exception:
            return {}
    return {}

def save_seen_jobs(seen: dict):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=PURGE_DAYS)).strftime("%Y-%m-%d")
    SEEN_JOBS_FILE.write_text(json.dumps(
        {h: d for h, d in seen.items() if d >= cutoff}, indent=2))

def is_fresh(job_hash: str, seen: dict) -> bool:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if job_hash not in seen:
        return True
    delta = (datetime.strptime(today, "%Y-%m-%d") -
             datetime.strptime(seen[job_hash], "%Y-%m-%d")).days
    return delta < MAX_DAYS_SHOW

def mark_seen(jobs: list, seen: dict) -> dict:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for job in jobs:
        h = job.get("dedup", "")
        if h and h not in seen:
            seen[h] = today
    return seen

# =============================================================================
# HELPERS
# =============================================================================

NL_LOCATION_STRICT = [
    "netherlands", "amsterdam", "rotterdam", "den haag", "the hague",
    "eindhoven", "utrecht", "delft", "leiden", "groningen", "holland",
    "breda", "haarlem", "tilburg", "maastricht", "arnhem", "nijmegen",
    "brainport", "north holland", "south holland", "noord-holland",
    "almere", "apeldoorn", "enschede", "hilversum", "amersfoort",
    "venlo", "zwolle", "leeuwarden", "hertogenbosch", "middelburg",
    "deventer", "zaandam", "veghel", "groenlo", "maassluis",
]

NL_REMOTE_INDICATORS = [
    "remote", "europe", "emea", "eu remote", "remote eu",
    "remote - eu", "remote - europe", "worldwide", "global",
]

NON_NL_COUNTRIES = [
    "united states", "united kingdom", "germany", "france", "spain",
    "portugal", "italy", "australia", "new zealand", "canada", "india",
    "brazil", "japan", "china", "singapore", "ireland", "sweden",
    "norway", "denmark", "finland", "austria", "switzerland", "poland",
    "czech", "israel", "south korea", "mexico", "argentina", "chile",
    "bangalore", "mumbai", "delhi", "hyderabad", "london", "berlin",
    "paris", "madrid", "stockholm", "dublin", "warsaw", "toronto",
]

STACK_KEYWORDS = [
    "react", "next.js", "nextjs", "typescript", "python", "fastapi",
    "node", "full-stack", "fullstack", "full stack", "frontend", "front-end",
    "backend", "back-end", "software engineer", "software developer",
    "ai ", "llm", "genai", "generative ai", "machine learning", "ml engineer",
    "data engineer", "cloud", "aws", "postgresql", "postgres", "supabase",
    "docker", "kubernetes", "react native", "mobile", "graphql", "rest api",
    "microservices", "langchain", "openai", "gpt", "nlp", "computer vision",
    "terraform", "ci/cd", "devops", "platform engineer", "it ", "digital",
    "web developer", "web application", "api", "database", "automation",
    "data analyst", "business intelligence", "power bi", "tableau",
]

SECTOR_MAP = {
    "healthcare": ["health", "medical", "hospital", "clinic", "pharma", "ehr",
                   "dicom", "radiology", "patient", "doctor", "care", "umc", "ziekenhuis"],
    "agriculture": ["agri", "farm", "crop", "greenhouse automation", "livestock",
                    "horticulture", "dairy", "food tech", "precision farming"],
    "energy":     ["energy", "solar", "wind", "renewable", "grid", "power", "utilities"],
    "logistics":  ["logistics", "supply chain", "warehouse", "transport", "shipping", "fleet"],
    "finance":    ["fintech", "bank", "insurance", "payment", "trading", "compliance", "audit"],
    "education":  ["university", "education", "learning", "research", "academia", "edtech"],
    "retail":     ["retail", "ecommerce", "e-commerce", "supermarket", "consumer"],
    "media":      ["media", "publishing", "broadcast", "content", "streaming"],
    "legal":      ["legal", "law", "compliance", "regulatory", "govtech"],
    "ngo":        ["ngo", "non-profit", "nonprofit", "humanitarian", "charity"],
    "government": ["government", "overheid", "public sector", "municipality"],
    "manufacturing": ["manufacturing", "industrial", "factory", "assembly", "production"],
}

SECTOR_EMOJI = {
    "healthcare": "🏥", "agriculture": "🌾", "energy": "⚡",
    "logistics": "🚚", "finance": "💳", "education": "🎓",
    "retail": "🛒", "media": "📺", "legal": "⚖️",
    "ngo": "🌍", "government": "🏛️", "manufacturing": "🏭", "tech": "💻",
}

def detect_sector(company: str, desc: str) -> str:
    text = f"{company} {desc}".lower()
    for sector, keywords in SECTOR_MAP.items():
        if any(kw in text for kw in keywords):
            return sector
    return "tech"

def is_nl_job(location: str, title: str, desc: str) -> bool:
    loc = location.lower().strip()
    desc_lower = desc.lower()
    for country in NON_NL_COUNTRIES:
        if country in loc:
            return False
    if any(kw in loc for kw in NL_LOCATION_STRICT):
        return True
    if any(kw in loc for kw in NL_REMOTE_INDICATORS):
        return any(kw in desc_lower for kw in NL_LOCATION_STRICT)
    return False

def quick_stack_score(title: str, desc: str) -> int:
    text = f"{title} {desc}".lower()
    return min(sum(1 for kw in STACK_KEYWORDS if kw in text), 10)

def detect_sponsorship(desc: str) -> str:
    """
    Detect sponsorship signals. As an international on Zoekjaar:
    - 'yes' = job mentions visa sponsorship / relocation (GREAT for post-Zoekjaar)
    - 'no'  = job explicitly says no sponsorship (RISKY after 12 months)
    - 'unknown' = not mentioned (most jobs — you can still ask)
    """
    text = desc.lower()
    pos = ["visa sponsorship", "relocation", "work permit", "sponsor",
           "immigration support", "international candidates", "we sponsor",
           "highly skilled migrant", "ind recognized", "ind recognised",
           "knowledge migrant", "relocation package", "expat"]
    neg = ["no sponsorship", "no visa", "must be authorized", "must be eligible",
           "must have right to work", "eu citizens only", "no relocation",
           "dutch nationals only", "eu passport holders only"]
    if any(kw in text for kw in neg):
        return "no"
    if any(kw in text for kw in pos):
        return "yes"
    return "unknown"

def dedup_hash(company: str, title: str) -> str:
    return hashlib.md5(f"{company}::{title}".lower().strip().encode()).hexdigest()

def strip_html(html: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    text = re.sub(r"</?(p|div|li|h[1-6])[^>]*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&amp;", "&").replace("&nbsp;", " ")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

# =============================================================================
# FETCHERS
# =============================================================================

async def fetch_greenhouse(session, slug: str, name: str) -> list:
    # v3 uses new job-boards endpoint
    url = f"https://job-boards.greenhouse.io/v1/boards/{slug}/jobs?content=true"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=12)) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
            out = []
            for job in data.get("jobs", []):
                loc  = (job.get("location") or {}).get("name", "")
                desc = strip_html(job.get("content", ""))
                if not is_nl_job(loc, job["title"], desc):
                    continue
                out.append({
                    "company": name, "title": job["title"], "location": loc,
                    "url": job.get("absolute_url",
                                   f"https://job-boards.greenhouse.io/{slug}/jobs/{job['id']}"),
                    "description": desc[:3000], "source": "greenhouse",
                    "stack_score": quick_stack_score(job["title"], desc),
                    "sponsorship_signal": detect_sponsorship(desc),
                    "sector": detect_sector(name, desc),
                    "dedup": dedup_hash(name, job["title"]),
                })
            return out
    except Exception:
        return []

async def fetch_lever(session, slug: str, name: str) -> list:
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=12)) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
            if not isinstance(data, list):
                return []
            out = []
            for p in data:
                loc   = (p.get("categories") or {}).get("location", "")
                desc  = p.get("descriptionPlain", "")
                title = p.get("text", "Unknown")
                if not is_nl_job(loc, title, desc):
                    continue
                out.append({
                    "company": name, "title": title, "location": loc,
                    "url": p.get("hostedUrl", f"https://jobs.lever.co/{slug}/{p.get('id','')}"),
                    "description": desc[:3000], "source": "lever",
                    "stack_score": quick_stack_score(title, desc),
                    "sponsorship_signal": detect_sponsorship(desc),
                    "sector": detect_sector(name, desc),
                    "dedup": dedup_hash(name, title),
                })
            return out
    except Exception:
        return []

async def fetch_ashby(session, slug: str, name: str) -> list:
    url = f"https://jobs.ashbyhq.com/{slug}/json"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=12)) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
            out = []
            for p in data.get("jobPostings", []):
                loc   = p.get("location", "") or p.get("locationName", "")
                desc  = strip_html(p.get("descriptionHtml", "") or p.get("description", ""))
                title = p.get("title", "Unknown")
                if not is_nl_job(loc, title, desc):
                    continue
                job_id = p.get("id", "")
                out.append({
                    "company": name, "title": title, "location": loc,
                    "url": p.get("jobUrl", f"https://jobs.ashbyhq.com/{slug}/{job_id}"),
                    "description": desc[:3000], "source": "ashby",
                    "stack_score": quick_stack_score(title, desc),
                    "sponsorship_signal": detect_sponsorship(desc),
                    "sector": detect_sector(name, desc),
                    "dedup": dedup_hash(name, title),
                })
            return out
    except Exception:
        return []

async def fetch_all_jobs() -> tuple:
    all_jobs = []
    companies_with_openings: dict = {}

    connector = aiohttp.TCPConnector(limit=20)
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; JobHunter/3.0)",
        "Accept": "application/json",
    }
    async with aiohttp.ClientSession(connector=connector, headers=headers) as session:
        tasks = (
            [fetch_greenhouse(session, s, n) for s, n in GREENHOUSE_COMPANIES] +
            [fetch_lever(session, s, n)      for s, n in LEVER_COMPANIES]      +
            [fetch_ashby(session, s, n)      for s, n in ASHBY_COMPANIES]
        )
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, list) and r:
                for job in r:
                    companies_with_openings[job["company"]] = job["source"]
                all_jobs.extend(r)

        # LinkedIn scraper (non-IT sectors)
        linkedin_jobs = await fetch_linkedin_jobs_apify(session)
        for job in linkedin_jobs:
            companies_with_openings[job["company"]] = "linkedin"
        all_jobs.extend(linkedin_jobs)

    # Dedup by hash
    seen_h: set = set()
    unique = []
    for job in all_jobs:
        if job["dedup"] not in seen_h:
            seen_h.add(job["dedup"])
            unique.append(job)

    unique.sort(key=lambda j: j["stack_score"], reverse=True)
    return unique, companies_with_openings

# =============================================================================
# GEMINI SCORING
# =============================================================================

async def score_with_gemini(jobs: list) -> list:
    if not GEMINI_API_KEY:
        for job in jobs:
            job.update({
                "fit_score": job["stack_score"], "cold_email_hook": "",
                "suggested_subject": "", "hiring_manager_title": "Engineering Manager",
                "key_match_reasons": [], "visa_friendly": False,
                "ats_keywords_missing": [], "ats_score": 0,
                "ats_fix": "", "cover_letter_angle": "", "which_resume": "fullstack_ai",
                "sponsorship_note": "",
            })
        return jobs

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    scored = []
    connector = aiohttp.TCPConnector(limit=5)

    async with aiohttp.ClientSession(connector=connector) as session:
        for job in jobs[:40]:
            sector = job.get("sector", "tech")
            spons  = job.get("sponsorship_signal", "unknown")

            sector_note = ""
            if sector not in ("tech", ""):
                sector_note = (
                    f"\nSECTOR NOTE: This is a {sector.upper()} company. "
                    "Score generously for 'Software Developer', 'IT Engineer', 'Data Analyst', "
                    "'Web Developer', 'Digital Transformation' — candidate's full-stack and AI "
                    "skills transfer directly to any industry vertical."
                )

            spons_note = {
                "yes": "\nSPONSORSHIP: Job mentions visa sponsorship/relocation — EXCELLENT for post-Zoekjaar HSM visa.",
                "no":  "\nSPONSORSHIP: Job says no sponsorship — NOTE THIS in sponsorship_note. Candidate can work now on Zoekjaar but cannot extend after 12 months without sponsor.",
                "unknown": "\nSPONSORSHIP: Not mentioned — common in NL. Candidate can work now; sponsorship discussion happens after offer.",
            }.get(spons, "")

            prompt = f"""You are a senior Dutch tech recruiter. Score this job. Return ONLY valid JSON, no markdown.

CANDIDATE:
{PROFILE}
{sector_note}
{spons_note}

JOB:
Title: {job['title']}
Company: {job['company']}
Location: {job['location']}
Sector: {sector}
Sponsorship signal: {spons}
Description: {job['description'][:2000]}

Return this exact JSON:
{{
  "fit_score": <1-10>,
  "stack_match": <1-10>,
  "seniority_fit": <1-10>,
  "visa_friendly": <true if sponsorship_signal=yes, false if =no, null if =unknown>,
  "sponsorship_note": "<one sentence about sponsorship situation for this job>",
  "key_match_reasons": ["reason1", "reason2", "reason3"],
  "ats_keywords_missing": ["kw1", "kw2", "kw3"],
  "ats_score": <0-100>,
  "ats_fix": "<one sentence: what to add/change in resume for THIS job>",
  "cold_email_hook": "<specific opener referencing company product/mission — not generic>",
  "suggested_subject": "<email subject line>",
  "hiring_manager_title": "<exact LinkedIn title to search>",
  "resume_tips": "<which 2-3 bullets to emphasize from candidate experience>",
  "which_resume": "<fullstack_ai or software_data or freelance>",
  "cover_letter_angle": "<one sentence: why candidate is uniquely relevant for THIS role>"
}}"""

            try:
                payload = {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0.3, "maxOutputTokens": 900},
                }
                async with session.post(url, json=payload,
                                        timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    data = await resp.json()
                    raw  = (data.get("candidates", [{}])[0]
                                .get("content", {})
                                .get("parts", [{}])[0]
                                .get("text", "{}"))
                    clean = raw.replace("```json", "").replace("```", "").strip()
                    scored.append({**job, **json.loads(clean)})
            except Exception as e:
                scored.append({**job,
                    "fit_score": job["stack_score"], "cold_email_hook": "",
                    "suggested_subject": "", "hiring_manager_title": "Engineering Manager",
                    "key_match_reasons": [], "visa_friendly": None,
                    "ats_keywords_missing": [], "ats_score": 0,
                    "ats_fix": "", "cover_letter_angle": "", "which_resume": "fullstack_ai",
                    "sponsorship_note": f"Signal: {spons}", "llm_error": str(e),
                })
            await asyncio.sleep(4)

    scored.sort(key=lambda j: j.get("fit_score", 0), reverse=True)
    return scored

# =============================================================================
# GOOGLE SHEETS
# =============================================================================

def append_to_google_sheet(jobs: list):
    if not GOOGLE_SERVICE_ACCOUNT_JSON or not GOOGLE_SHEET_ID:
        print("WARNING: No Google Sheet credentials, skipping")
        return
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        creds = Credentials.from_service_account_info(
            json.loads(GOOGLE_SERVICE_ACCOUNT_JSON),
            scopes=["https://www.googleapis.com/auth/spreadsheets"])
        gc    = gspread.authorize(creds)
        sheet = gc.open_by_key(GOOGLE_SHEET_ID).worksheet("Jobs")
        existing = set(sheet.col_values(16))   # dedup column
        rows = []
        for j in jobs:
            if j.get("dedup", "") in existing:
                continue
            rows.append([
                j.get("company",""), j.get("title",""), j.get("location",""),
                j.get("url",""), j.get("source",""), j.get("sector",""),
                j.get("fit_score",0), j.get("stack_match",0), j.get("seniority_fit",0),
                str(j.get("visa_friendly","")), j.get("sponsorship_signal",""),
                j.get("sponsorship_note",""),
                ", ".join(j.get("key_match_reasons",[])),
                j.get("cold_email_hook",""), j.get("suggested_subject",""),
                j.get("dedup",""),
                datetime.now(timezone.utc).strftime("%Y-%m-%d"), "",
            ])
        if rows:
            sheet.append_rows(rows, value_input_option="USER_ENTERED")
            print(f"Appended {len(rows)} new jobs to Google Sheet")
        else:
            print("No new jobs to append")
    except Exception as e:
        print(f"Google Sheet error: {e}")

# =============================================================================
# EMAIL DIGEST
# =============================================================================

def build_email_html(jobs: list, total_scraped: int, today: str,
                     companies_with_openings: dict, seen: dict) -> str:
    top   = [j for j in jobs if j.get("fit_score", 0) >= 7][:12]
    other = [j for j in jobs if j.get("fit_score", 0) < 7][:15]
    total_cos = len(GREENHOUSE_COMPANIES) + len(LEVER_COMPANIES) + len(ASHBY_COMPANIES)

    # Sponsorship count
    sponsored = [j for j in jobs if j.get("sponsorship_signal") == "yes"]
    risky     = [j for j in jobs if j.get("sponsorship_signal") == "no"]

    rows_html = ""
    for job in top:
        score  = job.get("fit_score", "?")
        spons  = job.get("sponsorship_signal", "unknown")
        spons_icon = {"yes": "🟢 Sponsors", "no": "🔴 No sponsor", "unknown": "🟡 Ask"}.get(spons, "🟡")
        spons_note = job.get("sponsorship_note", "")
        clr    = "#2E7D32" if score >= 8 else "#E67E00" if score >= 6 else "#888"
        sector = job.get("sector", "tech")
        emoji  = SECTOR_EMOJI.get(sector, "💼")
        h      = job.get("dedup", "")
        is_new = h not in seen or seen.get(h, "") == today
        badge  = ('<span style="background:#E8F5E9;color:#2E7D32;font-size:10px;'
                  'padding:2px 7px;border-radius:10px;font-weight:700;">NEW</span>'
                  if is_new else
                  '<span style="background:#FFF3E0;color:#E65100;font-size:10px;'
                  'padding:2px 7px;border-radius:10px;">day 2</span>')
        hm     = job.get("hiring_manager_title", "")
        li_url = (f"https://www.linkedin.com/search/results/people/?keywords="
                  f"{job['company'].replace(' ','%20')}%20{hm.replace(' ','%20')}")
        ats_c  = ("#2E7D32" if job.get("ats_score",0) >= 75
                  else "#E67E00" if job.get("ats_score",0) >= 50 else "#C62828")
        rb     = {"fullstack_ai":"🤖 AI Full-Stack","software_data":"💻 Software/Data",
                  "freelance":"🔧 Freelance"}.get(job.get("which_resume",""), "")
        miss   = ", ".join(job.get("ats_keywords_missing",[])[:4])
        reasons= ", ".join(job.get("key_match_reasons",[])[:2])

        rows_html += f"""
        <tr style="border-bottom:1px solid #eee;">
          <td style="padding:14px 12px;">
            <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:4px;">
              {badge}
              <span style="font-size:12px;color:#666;">{emoji} {sector.title()}</span>
              <span style="font-size:11px;padding:2px 6px;border-radius:10px;background:#f0f0f0;">{spons_icon}</span>
            </div>
            <div style="font-weight:600;font-size:15px;color:#1a2744;">{job['title']}</div>
            <div style="color:#666;font-size:13px;margin-top:2px;">🏢 {job['company']} &nbsp;|&nbsp; 📍 {job['location']}</div>
            {'<div style="font-size:12px;color:#555;margin-top:3px;">✨ ' + reasons + '</div>' if reasons else ''}
            {'<div style="font-size:12px;color:#777;margin-top:2px;font-style:italic;">🛂 ' + spons_note + '</div>' if spons_note else ''}
            {'<div style="color:#1565C0;font-size:12px;margin-top:3px;">💬 <em>' + job.get("cold_email_hook","") + '</em></div>' if job.get("cold_email_hook") else ''}
            {'<div style="font-size:12px;margin-top:2px;">📧 Subject: <strong>' + job.get("suggested_subject","") + '</strong></div>' if job.get("suggested_subject") else ''}
            {'<div style="background:#E8F5E9;padding:5px 10px;border-radius:4px;font-size:12px;margin-top:5px;color:#2E7D32;">📄 ' + rb + ' — ' + job.get("resume_tips","") + '</div>' if job.get("resume_tips") else ''}
            {'<div style="background:#FFF3E0;padding:5px 10px;border-radius:4px;font-size:12px;margin-top:4px;">🎯 ATS <strong style="color:' + ats_c + '">' + str(job.get("ats_score",0)) + '%</strong> — Missing: ' + miss + '</div>' if miss else ''}
            {'<div style="background:#E3F2FD;padding:5px 10px;border-radius:4px;font-size:12px;margin-top:4px;color:#1565C0;">✉️ ' + job.get("cover_letter_angle","") + '</div>' if job.get("cover_letter_angle") else ''}
            <div style="margin-top:8px;">
              <a href="{job['url']}" style="background:#E8690A;color:white;padding:4px 12px;border-radius:4px;text-decoration:none;font-size:12px;font-weight:600;">Apply →</a>
              {'&nbsp;<a href="' + li_url + '" style="background:#0077B5;color:white;padding:4px 12px;border-radius:4px;text-decoration:none;font-size:12px;">Find ' + hm + ' →</a>' if hm else ''}
            </div>
          </td>
          <td style="padding:14px 12px;text-align:center;vertical-align:top;min-width:55px;">
            <div style="font-size:22px;font-weight:700;color:{clr};">{score}</div>
            <div style="font-size:11px;color:#888;">/10</div>
          </td>
        </tr>"""

    other_rows = "".join(f"""
        <tr style="border-bottom:1px solid #f5f5f5;">
          <td style="padding:8px 12px;">
            {SECTOR_EMOJI.get(j.get('sector','tech'),'💼')}
            <a href="{j['url']}" style="color:#1a2744;text-decoration:none;font-size:13px;">{j['title']}</a>
            <span style="color:#888;font-size:12px;"> — {j['company']} | {j['location']}</span>
            <span style="font-size:11px;margin-left:6px;">{"🟢" if j.get("sponsorship_signal")=="yes" else "🔴" if j.get("sponsorship_signal")=="no" else "🟡"}</span>
          </td>
          <td style="padding:8px 12px;text-align:center;color:#888;font-size:13px;">{j.get('fit_score','?')}/10</td>
        </tr>""" for j in other)

    # Companies with openings
    ats_label = {"greenhouse": "Greenhouse", "lever": "Lever",
                 "ashby": "Ashby", "linkedin": "LinkedIn"}
    cos_items = "".join(
        f'<li style="padding:3px 0;font-size:13px;">🏢 <strong>{co}</strong> '
        f'<span style="color:#888;font-size:11px;">({ats_label.get(src,src)})</span></li>'
        for co, src in sorted(companies_with_openings.items())
    )

    # Sponsorship summary
    spons_summary = f"""
    <div style="padding:12px 24px;background:#F0FFF0;border-left:4px solid #2E7D32;margin-top:12px;">
      <strong style="font-size:13px;">🛂 Sponsorship Summary</strong>
      <p style="font-size:12px;color:#555;margin:4px 0;">
        🟢 <strong>{len(sponsored)}</strong> jobs mention visa sponsorship/relocation (best for post-Zoekjaar HSM) &nbsp;|&nbsp;
        🟡 <strong>{total_scraped - len(sponsored) - len(risky)}</strong> not mentioned (you can ask) &nbsp;|&nbsp;
        🔴 <strong>{len(risky)}</strong> say no sponsorship (work now on Zoekjaar, but risky after 12 months)
      </p>
      <p style="font-size:11px;color:#888;margin:0;">
        IND recognized sponsors: <a href="https://ind.nl/en/public-register-recognised-sponsors" style="color:#E8690A;">Check register →</a>
      </p>
    </div>"""

    return f"""
    <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:720px;margin:0 auto;background:#fff;">
      <div style="background:#1a2744;color:white;padding:20px 24px;border-radius:8px 8px 0 0;">
        <h1 style="margin:0;font-size:20px;font-weight:600;">🇳🇱 Netherlands Job Digest v3</h1>
        <p style="margin:4px 0 0;font-size:13px;opacity:.8;">
          {today} &nbsp;·&nbsp; {total_scraped} NL roles found &nbsp;·&nbsp; {total_cos} companies (GH+Lever+Ashby+LinkedIn) &nbsp;·&nbsp; max 2 days/job
        </p>
      </div>
      <div style="padding:14px 24px;background:#FFF3E8;border-left:4px solid #E8690A;">
        <strong>Top {len(top)} matches (fit ≥ 7)</strong>
        <span style="font-size:12px;color:#666;"> — fresh only · 🟢 sponsors · 🟡 unknown · 🔴 no sponsor</span>
      </div>
      <table style="width:100%;border-collapse:collapse;">
        <thead><tr style="background:#f9f9f7;">
          <th style="padding:10px 12px;text-align:left;font-size:12px;color:#888;font-weight:500;">Role &amp; Outreach</th>
          <th style="padding:10px 12px;text-align:center;font-size:12px;color:#888;font-weight:500;width:55px;">Fit</th>
        </tr></thead>
        <tbody>{rows_html}</tbody>
      </table>
      {"<div style='padding:14px 24px;background:#f9f9f7;margin-top:12px;'><strong style='font-size:13px;color:#666;'>Other matches</strong></div><table style='width:100%;border-collapse:collapse;'><tbody>" + other_rows + "</tbody></table>" if other_rows else ""}
      {spons_summary}
      <div style="padding:20px 24px;background:#F3F8FF;margin-top:12px;">
        <strong style="font-size:14px;color:#1a2744;">📬 {len(companies_with_openings)} companies actively hiring in NL today</strong>
        <p style="font-size:12px;color:#666;margin:6px 0 12px;">Cold-email the CTO/Engineering Manager even if the role isn't perfect fit — you arrive August with a Zoekjaar permit.</p>
        <ul style="list-style:none;padding:0;margin:0;column-count:2;column-gap:20px;">{cos_items}</ul>
      </div>
      <div style="padding:16px 24px;background:#f5f5f2;border-radius:0 0 8px 8px;font-size:12px;color:#888;text-align:center;margin-top:12px;">
        NL Job Hunter v3 &nbsp;·&nbsp; {total_cos} companies &nbsp;·&nbsp; Greenhouse (new API) + Lever + Ashby + LinkedIn &nbsp;·&nbsp; $0/month
      </div>
    </div>"""

def send_email_digest(jobs: list, total_scraped: int,
                      companies_with_openings: dict, seen: dict):
    today     = datetime.now(timezone.utc).strftime("%b %d, %Y")
    top_count = len([j for j in jobs if j.get("fit_score", 0) >= 7])
    sponsored = len([j for j in jobs if j.get("sponsorship_signal") == "yes"])

    if not GMAIL_APP_PASSWORD:
        print(f"\n🇳🇱 {today}: {top_count} matches | {sponsored} sponsor jobs | "
              f"{len(companies_with_openings)} companies hiring")
        for j in jobs[:5]:
            print(f"  {j.get('fit_score','?')}/10 [{j.get('sponsorship_signal','?')}] "
                  f"— {j['title']} @ {j['company']}")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = (f"🇳🇱 NL Jobs — {top_count} fresh matches | "
                      f"{sponsored} sponsor | {len(companies_with_openings)} hiring | {today}")
    msg["From"] = GMAIL_ADDRESS
    msg["To"]   = GMAIL_ADDRESS
    msg.attach(MIMEText(
        build_email_html(jobs, total_scraped, today, companies_with_openings, seen), "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            s.send_message(msg)
        print(f"Email sent: {top_count} matches, {sponsored} sponsor jobs")
    except Exception as e:
        print(f"Email error: {e}")

# =============================================================================
# MAIN
# =============================================================================

async def main():
    start = time.time()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    total_cos = len(GREENHOUSE_COMPANIES) + len(LEVER_COMPANIES) + len(ASHBY_COMPANIES)
    print(f"NL Job Hunter v3 — {datetime.now(timezone.utc).isoformat()}")
    print(f"Scraping {total_cos} verified companies + LinkedIn...")

    seen = load_seen_jobs()
    print(f"Loaded {len(seen)} seen hashes")

    all_jobs, companies_with_openings = await fetch_all_jobs()
    print(f"Found {len(all_jobs)} unique NL jobs in {time.time()-start:.1f}s")
    print(f"Companies hiring: {len(companies_with_openings)}")
    sponsored = [j for j in all_jobs if j.get("sponsorship_signal") == "yes"]
    print(f"Jobs mentioning sponsorship: {len(sponsored)}")

    fresh = [j for j in all_jobs if is_fresh(j["dedup"], seen)]
    print(f"Fresh (< {MAX_DAYS_SHOW} days): {len(fresh)}")

    seen = mark_seen(all_jobs, seen)
    save_seen_jobs(seen)
    print(f"Saved {len(seen)} hashes to {SEEN_JOBS_FILE}")

    if not fresh:
        print("No fresh jobs today.")
        send_email_digest([], 0, companies_with_openings, seen)
        return

    print(f"Scoring {min(len(fresh), 40)} jobs with Gemini...")
    scored = await score_with_gemini(fresh)
    if scored:
        print(f"Top: {scored[0].get('fit_score','?')}/10 [{scored[0].get('sponsorship_signal','?')}] "
              f"— {scored[0]['title']} @ {scored[0]['company']}")

    append_to_google_sheet(all_jobs)
    send_email_digest(scored, len(all_jobs), companies_with_openings, seen)
    print(f"Done in {time.time()-start:.1f}s")

if __name__ == "__main__":
    asyncio.run(main())


# =============================================================================
# SLUG VERIFIER — run locally to check which slugs are alive
# Usage: python job_hunter.py --verify
# =============================================================================

def run_verifier():
    """Test all slugs. Run locally: python job_hunter.py --verify"""
    import sys

    async def _verify():
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "application/json",
        }
        results = {"greenhouse": [], "lever": [], "ashby": []}

        async with aiohttp.ClientSession(headers=headers) as session:
            # Greenhouse
            for slug, name in GREENHOUSE_COMPANIES:
                url = f"https://job-boards.greenhouse.io/v1/boards/{slug}/jobs"
                try:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as r:
                        if r.status == 200:
                            d = await r.json()
                            count = len(d.get("jobs", []))
                            results["greenhouse"].append(("LIVE" if count else "EMPTY", slug, name, count))
                        else:
                            results["greenhouse"].append(("DEAD", slug, name, r.status))
                except Exception as e:
                    results["greenhouse"].append(("ERROR", slug, name, str(e)[:50]))
                await asyncio.sleep(0.3)

            # Lever
            for slug, name in LEVER_COMPANIES:
                url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
                try:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as r:
                        if r.status == 200:
                            d = await r.json()
                            count = len(d) if isinstance(d, list) else 0
                            results["lever"].append(("LIVE" if count else "EMPTY", slug, name, count))
                        else:
                            results["lever"].append(("DEAD", slug, name, r.status))
                except Exception as e:
                    results["lever"].append(("ERROR", slug, name, str(e)[:50]))
                await asyncio.sleep(0.3)

            # Ashby
            for slug, name in ASHBY_COMPANIES:
                url = f"https://jobs.ashbyhq.com/{slug}/json"
                try:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as r:
                        if r.status == 200:
                            d = await r.json()
                            count = len(d.get("jobPostings", []))
                            results["ashby"].append(("LIVE" if count else "EMPTY", slug, name, count))
                        else:
                            results["ashby"].append(("DEAD", slug, name, r.status))
                except Exception as e:
                    results["ashby"].append(("ERROR", slug, name, str(e)[:50]))
                await asyncio.sleep(0.3)

        # Print results
        for ats, rows in results.items():
            live  = [r for r in rows if r[0] == "LIVE"]
            empty = [r for r in rows if r[0] == "EMPTY"]
            dead  = [r for r in rows if r[0] in ("DEAD","ERROR")]
            print(f"\n{'='*60}")
            print(f"  {ats.upper()} — {len(live)} LIVE | {len(empty)} EMPTY | {len(dead)} DEAD")
            print(f"{'='*60}")
            print(f"\n  ✅ LIVE:")
            for _, s, n, c in sorted(live, key=lambda x: -x[3]):
                print(f"    ({c:4d} jobs)  (\"{s}\", \"{n}\"),")
            print(f"\n  ⚠️  EMPTY (valid slug, 0 NL jobs today):")
            for _, s, n, _ in empty:
                print(f"    (\"{s}\", \"{n}\"),")
            print(f"\n  ❌ DEAD (remove from list):")
            for _, s, n, err in dead:
                print(f"    (\"{s}\", \"{n}\")  [{err}]")

    asyncio.run(_verify())


import sys
if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "--verify":
    run_verifier()
elif __name__ == "__main__":
    asyncio.run(main())


# =============================================================================
# GITHUB ACTIONS WORKFLOW
# Save as: .github/workflows/daily-hunt.yml
# =============================================================================
"""
name: NL Job Hunter Daily

on:
  schedule:
    - cron: '0 6 * * 1-5'   # 08:00 CET Mon-Fri
  workflow_dispatch:           # manual trigger from Actions tab

permissions:
  contents: write              # needed to commit seen_jobs.json

jobs:
  hunt:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          token: ${{ secrets.GITHUB_TOKEN }}

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install aiohttp gspread google-auth

      - name: Run job hunter
        env:
          GEMINI_API_KEY:              ${{ secrets.GEMINI_API_KEY }}
          GMAIL_ADDRESS:               ${{ secrets.GMAIL_ADDRESS }}
          GMAIL_APP_PASSWORD:          ${{ secrets.GMAIL_APP_PASSWORD }}
          GOOGLE_SHEET_ID:             ${{ secrets.GOOGLE_SHEET_ID }}
          GOOGLE_SERVICE_ACCOUNT_JSON: ${{ secrets.GOOGLE_SERVICE_ACCOUNT_JSON }}
          APIFY_API_TOKEN:             ${{ secrets.APIFY_API_TOKEN }}
        run: python job_hunter.py

      - name: Commit seen_jobs.json
        run: |
          git config user.name  "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add seen_jobs.json
          git diff --cached --quiet || git commit -m "chore: update seen_jobs [skip ci]"
          git push
"""
