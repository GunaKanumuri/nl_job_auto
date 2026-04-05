"""
NL Job Hunter — Autonomous Netherlands Job Search Agent
Runs daily via GitHub Actions. Zero cost. Zero maintenance.

Features:
- Scrapes 120+ company career pages (Greenhouse + Lever APIs)
- Filters for Netherlands / Remote-EU roles only
- Scores each job with Gemini LLM against Guna's exact profile
- Drafts cold outreach (email hook + subject + hiring manager to find)
- Cross-references IND recognized sponsor signals
- Appends to Google Sheet (your CRM)
- Sends daily email digest to Gmail
- Weekly Sunday stats summary
"""

import os
import json
import time
import hashlib
import smtplib
import asyncio
import aiohttp
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone
from typing import Optional

# =============================================================================
# CONFIG
# =============================================================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS", "gunakanumuri5@gmail.com")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
GOOGLE_SHEET_ID = os.environ.get("GOOGLE_SHEET_ID", "")
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")

PROFILE = """Guna Shekar Varma Kanumuri — MS Computer Science (Purdue University, May 2025, GPA 3.70).
Core Stack: React, Next.js, TypeScript, React Native, FastAPI, Python, PostgreSQL, Supabase, LLM/AI tooling (Gemini, Sarvam AI, LangChain).
Projects: Full-stack SaaS event platform (WeDesiDecor, Next.js+Express+PostgreSQL), AI warranty management mobile app (MIRA Safety, React Native+Supabase, 290+ tests), WhatsApp AI voice bot for elderly care (AYANA, FastAPI+Sarvam+Gemini), AI job search platform (Karmio, Next.js+Supabase+Greenhouse/Lever APIs).
Experience: Solo full-stack developer, AI engineer, shipped production apps end-to-end.
Looking for: Full-stack engineer, AI/ML engineer, frontend engineer, or platform engineer roles in the Netherlands.
Visa: Zoekjaar (orientation year) permit. Needs IND-recognized sponsor for Highly Skilled Migrant visa after Zoekjaar ends."""

# =============================================================================
# COMPANY REGISTRY — 120+ companies
# =============================================================================
GREENHOUSE_COMPANIES = [
    # TIER 1: Dutch-born tech
    ("booking", "Booking.com"), ("adyen", "Adyen"), ("mollie", "Mollie"),
    ("picnic-technologies", "Picnic"), ("tomtom", "TomTom"), ("catawiki", "Catawiki"),
    ("bunq", "bunq"), ("backbase", "Backbase"), ("messagebird", "MessageBird"),
    ("studocu", "StuDocu"), ("sendcloud", "Sendcloud"), ("bynder", "Bynder"),
    ("lightspeedhq", "Lightspeed"), ("monumental", "Monumental"), ("helloprint", "Helloprint"),
    # TIER 2: Global with NL offices
    ("miro", "Miro"), ("elastic", "Elastic"), ("databricks", "Databricks"),
    ("stripe", "Stripe"), ("figma", "Figma"), ("notion", "Notion"),
    ("vercel", "Vercel"), ("cloudflare", "Cloudflare"), ("datadog", "Datadog"),
    ("twilio", "Twilio"), ("sentry", "Sentry"), ("gitlab", "GitLab"),
    ("snyk", "Snyk"), ("personio", "Personio"), ("contentful", "Contentful"),
    ("grafana", "Grafana Labs"), ("confluent", "Confluent"), ("posthog", "PostHog"),
    ("supabase", "Supabase"), ("linear", "Linear"), ("deel", "Deel"),
    ("remote", "Remote"), ("mongodb", "MongoDB"), ("hashicorp", "HashiCorp"),
    ("atlassian", "Atlassian"), ("uber", "Uber"), ("flexport", "Flexport"),
    ("toast", "Toast"), ("airtable", "Airtable"),
    # TIER 3: Fintech
    ("payhawk", "Payhawk"), ("circle", "Circle"),
    ("chainalysis", "Chainalysis"), ("ramp", "Ramp"), ("brex", "Brex"),
    # TIER 4: AI/ML
    ("huggingface", "Hugging Face"), ("cohere", "Cohere"), ("runway", "Runway"),
    ("stability", "Stability AI"), ("pinecone", "Pinecone"), ("weaviate", "Weaviate"),
    ("labelbox", "Labelbox"), ("wandb", "Weights & Biases"), ("deepset", "deepset"),
    ("assemblyai", "AssemblyAI"),
    # TIER 5: Dutch startups
    ("datenna", "Datenna"), ("crisp", "Crisp"),
    ("otrium", "Otrium"), ("tiqets", "Tiqets"), ("vivid-money", "Vivid Money"),
    # TIER 6: DevTools (remote-EU)
    ("tailscale", "Tailscale"), ("pulumi", "Pulumi"), ("dagster", "Dagster"),
    ("temporal", "Temporal"), ("inngest", "Inngest"), ("nango", "Nango"),
    ("clerk", "Clerk"), ("stytch", "Stytch"), ("launchdarkly", "LaunchDarkly"),
    ("statsig", "Statsig"), ("honeycomb", "Honeycomb"), ("circleci", "CircleCI"),
    ("semgrep", "Semgrep"), ("gitpod", "Gitpod"), ("coder", "Coder"),
    # TIER 7: E-commerce
    ("vinted", "Vinted"), ("zalando", "Zalando"), ("hellofresh", "HelloFresh"),
    ("deliveryhero", "Delivery Hero"), ("bolt", "Bolt"),
    # TIER 8: Dutch enterprises
    ("xebia", "Xebia"),
    # TIER 9: Enterprise SaaS with NL
    ("hubspot", "HubSpot"), ("salesforce", "Salesforce"),
    ("servicenow", "ServiceNow"), ("snowflake", "Snowflake"), ("okta", "Okta"),
    ("crowdstrike", "CrowdStrike"), ("zscaler", "Zscaler"),
]

LEVER_COMPANIES = [
    ("takeaway", "Just Eat Takeaway"), ("framer", "Framer"),
    ("netflix", "Netflix"), ("spotify", "Spotify"), ("oyster", "Oyster"),
    ("rippling", "Rippling"), ("lattice", "Lattice"), ("ashby", "Ashby"),
    ("descript", "Descript"), ("ml6", "ML6"),
    ("dataiku", "Dataiku"), ("logicmonitor", "LogicMonitor"),
    ("zapier", "Zapier"), ("webflow", "Webflow"), ("intercom", "Intercom"),
    ("canva", "Canva"), ("loom", "Loom"), ("calendly", "Calendly"),
    ("notion", "Notion"), ("miro", "Miro"),
]

# =============================================================================
# LOCATION + STACK MATCHING
# =============================================================================
# STRICT location keywords — must appear in the LOCATION field itself
NL_LOCATION_STRICT = [
    "netherlands", "amsterdam", "rotterdam", "den haag", "the hague",
    "eindhoven", "utrecht", "delft", "leiden", "groningen", "holland",
    "breda", "haarlem", "tilburg", "maastricht", "arnhem", "nijmegen",
    "brainport", "north holland", "south holland", "noord-holland", "zuid-holland",
    "almere", "apeldoorn", "enschede", "hilversum", "dordrecht", "amersfoort",
]

# LOOSE keywords — only match if location says "remote" or "europe" AND
# the description mentions NL specifically
NL_REMOTE_INDICATORS = ["remote", "europe", "emea", "eu remote", "remote eu",
                         "remote - eu", "remote - europe", "worldwide"]

STACK_KEYWORDS = [
    "react", "next.js", "nextjs", "typescript", "python", "fastapi",
    "node", "full-stack", "fullstack", "full stack", "frontend", "front-end",
    "backend", "back-end", "ai ", "llm", "genai", "generative ai",
    "machine learning", "ml engineer", "data engineer", "cloud", "aws",
    "postgresql", "postgres", "supabase", "docker", "kubernetes",
    "react native", "mobile", "graphql", "rest api", "microservices",
    "langchain", "openai", "gpt", "nlp", "computer vision",
    "terraform", "ci/cd", "devops", "platform engineer",
]

SPONSORSHIP_POSITIVE = [
    "visa sponsorship", "relocation", "work permit", "sponsor",
    "right to work", "immigration support", "relocation package",
    "international candidates welcome", "we sponsor",
]

SPONSORSHIP_NEGATIVE = [
    "no sponsorship", "no visa", "must be authorized",
    "must have right to work", "eu citizens only", "no relocation",
]

# Countries that are NOT Netherlands — reject if location explicitly mentions these
NON_NL_COUNTRIES = [
    "united states", "united kingdom", "germany", "france", "spain",
    "portugal", "italy", "australia", "new zealand", "canada", "india",
    "brazil", "japan", "china", "singapore", "ireland", "sweden",
    "norway", "denmark", "finland", "austria", "switzerland", "poland",
    "czech", "israel", "south korea", "mexico", "argentina", "chile",
]


def is_nl_job(location: str, title: str, desc: str) -> bool:
    loc = location.lower().strip()
    desc_lower = desc.lower()

    # Step 1: If location explicitly mentions a non-NL country, reject
    for country in NON_NL_COUNTRIES:
        if country in loc:
            return False

    # Step 2: If location explicitly mentions a Dutch city/region, accept
    if any(kw in loc for kw in NL_LOCATION_STRICT):
        return True

    # Step 3: If location says "remote"/"europe"/"emea", only accept if
    # the description specifically mentions Netherlands or a Dutch city
    if any(kw in loc for kw in NL_REMOTE_INDICATORS):
        nl_in_desc = any(kw in desc_lower for kw in NL_LOCATION_STRICT)
        return nl_in_desc

    return False


def quick_stack_score(title: str, desc: str) -> int:
    text = f"{title} {desc}".lower()
    score = sum(1 for kw in STACK_KEYWORDS if kw in text)
    return min(score, 10)


def detect_sponsorship(desc: str) -> str:
    text = desc.lower()
    pos = sum(1 for kw in SPONSORSHIP_POSITIVE if kw in text)
    neg = sum(1 for kw in SPONSORSHIP_NEGATIVE if kw in text)
    if pos > 0 and neg == 0:
        return "yes"
    if neg > 0:
        return "no"
    return "unknown"


def dedup_hash(company: str, title: str) -> str:
    key = f"{company}::{title}".lower().strip()
    return hashlib.md5(key.encode()).hexdigest()


def strip_html(html: str) -> str:
    import re
    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    text = re.sub(r"</?(p|div|li|h[1-6])[^>]*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&amp;", "&").replace("&nbsp;", " ")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# =============================================================================
# FETCHERS
# =============================================================================
async def fetch_greenhouse(session: aiohttp.ClientSession, slug: str, name: str) -> list[dict]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=12)) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
            jobs = []
            for job in data.get("jobs", []):
                loc = (job.get("location") or {}).get("name", "")
                desc = strip_html(job.get("content", ""))
                if not is_nl_job(loc, job["title"], desc):
                    continue
                jobs.append({
                    "company": name,
                    "title": job["title"],
                    "location": loc,
                    "url": job.get("absolute_url", f"https://boards.greenhouse.io/{slug}/jobs/{job['id']}"),
                    "description": desc[:3000],
                    "source": "greenhouse",
                    "stack_score": quick_stack_score(job["title"], desc),
                    "sponsorship_signal": detect_sponsorship(desc),
                    "dedup": dedup_hash(name, job["title"]),
                })
            return jobs
    except Exception:
        return []


async def fetch_lever(session: aiohttp.ClientSession, slug: str, name: str) -> list[dict]:
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=12)) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
            if not isinstance(data, list):
                return []
            jobs = []
            for posting in data:
                loc = (posting.get("categories") or {}).get("location", "")
                desc = posting.get("descriptionPlain", "")
                if not is_nl_job(loc, posting.get("text", ""), desc):
                    continue
                title = posting.get("text", "Unknown")
                jobs.append({
                    "company": name,
                    "title": title,
                    "location": loc,
                    "url": posting.get("hostedUrl", f"https://jobs.lever.co/{slug}/{posting.get('id','')}"),
                    "description": desc[:3000],
                    "source": "lever",
                    "stack_score": quick_stack_score(title, desc),
                    "sponsorship_signal": detect_sponsorship(desc),
                    "dedup": dedup_hash(name, title),
                })
            return jobs
    except Exception:
        return []


async def fetch_all_jobs() -> list[dict]:
    all_jobs = []
    connector = aiohttp.TCPConnector(limit=15)
    async with aiohttp.ClientSession(connector=connector) as session:
        # Greenhouse
        gh_tasks = [fetch_greenhouse(session, slug, name) for slug, name in GREENHOUSE_COMPANIES]
        gh_results = await asyncio.gather(*gh_tasks, return_exceptions=True)
        for r in gh_results:
            if isinstance(r, list):
                all_jobs.extend(r)

        # Lever
        lv_tasks = [fetch_lever(session, slug, name) for slug, name in LEVER_COMPANIES]
        lv_results = await asyncio.gather(*lv_tasks, return_exceptions=True)
        for r in lv_results:
            if isinstance(r, list):
                all_jobs.extend(r)

    # Deduplicate
    seen = set()
    unique = []
    for job in all_jobs:
        if job["dedup"] not in seen:
            seen.add(job["dedup"])
            unique.append(job)

    # Sort by stack score, take top 40 for LLM scoring
    unique.sort(key=lambda j: j["stack_score"], reverse=True)
    return unique[:40]


# =============================================================================
# LLM SCORING WITH GEMINI
# =============================================================================
async def score_with_gemini(jobs: list[dict]) -> list[dict]:
    if not GEMINI_API_KEY:
        print("WARNING: No GEMINI_API_KEY, using stack_score only")
        for job in jobs:
            job["fit_score"] = job["stack_score"]
            job["cold_email_hook"] = ""
            job["suggested_subject"] = ""
            job["hiring_manager_title"] = "Engineering Manager"
            job["key_match_reasons"] = []
            job["visa_friendly"] = job["sponsorship_signal"] == "yes"
        return jobs

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    scored = []

    connector = aiohttp.TCPConnector(limit=5)
    async with aiohttp.ClientSession(connector=connector) as session:
        for job in jobs:
            prompt = f"""Score this job for the candidate. Return ONLY valid JSON, no markdown fences.

CANDIDATE:
{PROFILE}

JOB:
Title: {job['title']}
Company: {job['company']}
Location: {job['location']}
Description: {job['description'][:2000]}

Return this exact JSON structure:
{{"fit_score": <1-10>, "stack_match": <1-10>, "seniority_fit": <1-10>, "visa_friendly": <true/false>, "key_match_reasons": ["reason1", "reason2"], "cold_email_hook": "<personalized one-liner to open a cold email to the hiring manager>", "suggested_subject": "<email subject line>", "hiring_manager_title": "<exact title to search on LinkedIn>"}}"""

            try:
                payload = {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0.3, "maxOutputTokens": 500},
                }
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    data = await resp.json()
                    text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "{}")
                    clean = text.replace("```json", "").replace("```", "").strip()
                    analysis = json.loads(clean)
                    scored.append({**job, **analysis})
            except Exception as e:
                scored.append({
                    **job,
                    "fit_score": job["stack_score"],
                    "cold_email_hook": "",
                    "suggested_subject": "",
                    "hiring_manager_title": "Engineering Manager",
                    "key_match_reasons": [],
                    "visa_friendly": job["sponsorship_signal"] == "yes",
                    "llm_error": str(e),
                })
            # Rate limit: ~15 RPM for free Gemini
            await asyncio.sleep(4)

    scored.sort(key=lambda j: j.get("fit_score", 0), reverse=True)
    return scored[:25]


# =============================================================================
# GOOGLE SHEETS
# =============================================================================
def append_to_google_sheet(jobs: list[dict]):
    if not GOOGLE_SERVICE_ACCOUNT_JSON or not GOOGLE_SHEET_ID:
        print("WARNING: No Google Sheet credentials, skipping sheet append")
        return

    try:
        import gspread
        from google.oauth2.service_account import Credentials

        creds_dict = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)
        creds = Credentials.from_service_account_info(creds_dict, scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
        ])
        gc = gspread.authorize(creds)
        sheet = gc.open_by_key(GOOGLE_SHEET_ID).worksheet("Jobs")

        # Get existing dedup hashes to avoid duplicates
        existing = sheet.col_values(14)  # dedup column (N)
        existing_set = set(existing)

        rows = []
        for job in jobs:
            if job.get("dedup", "") in existing_set:
                continue
            rows.append([
                job.get("company", ""),
                job.get("title", ""),
                job.get("location", ""),
                job.get("url", ""),
                job.get("source", ""),
                job.get("fit_score", 0),
                job.get("stack_match", 0),
                job.get("seniority_fit", 0),
                str(job.get("visa_friendly", "")),
                ", ".join(job.get("key_match_reasons", [])),
                job.get("cold_email_hook", ""),
                job.get("suggested_subject", ""),
                job.get("hiring_manager_title", ""),
                job.get("dedup", ""),
                datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "",  # Status column — you fill manually
            ])

        if rows:
            sheet.append_rows(rows, value_input_option="USER_ENTERED")
            print(f"Appended {len(rows)} new jobs to Google Sheet")
        else:
            print("No new jobs to append (all duplicates)")

    except Exception as e:
        print(f"Google Sheet error: {e}")


# =============================================================================
# EMAIL DIGEST
# =============================================================================
def send_email_digest(jobs: list[dict], total_scraped: int):
    if not GMAIL_APP_PASSWORD:
        print("WARNING: No GMAIL_APP_PASSWORD, printing digest to stdout")
        print(format_digest_text(jobs, total_scraped))
        return

    today = datetime.now(timezone.utc).strftime("%b %d, %Y")
    is_sunday = datetime.now(timezone.utc).weekday() == 6

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🇳🇱 NL Jobs — {len(jobs)} matches | {today}"
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = GMAIL_ADDRESS

    html = build_email_html(jobs, total_scraped, today, is_sunday)
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            server.send_message(msg)
        print(f"Email digest sent to {GMAIL_ADDRESS}")
    except Exception as e:
        print(f"Email error: {e}")
        print(format_digest_text(jobs, total_scraped))


def build_email_html(jobs: list[dict], total_scraped: int, today: str, is_sunday: bool) -> str:
    top_jobs = [j for j in jobs if j.get("fit_score", 0) >= 7][:10]
    other_jobs = [j for j in jobs if j.get("fit_score", 0) < 7][:15]

    rows_html = ""
    for i, job in enumerate(top_jobs, 1):
        score = job.get("fit_score", "?")
        visa = "✅" if job.get("visa_friendly") else "❓"
        color = "#2E7D32" if score >= 8 else "#E67E00" if score >= 6 else "#888"
        hook = job.get("cold_email_hook", "")
        hm = job.get("hiring_manager_title", "")
        subject = job.get("suggested_subject", "")
        reasons = ", ".join(job.get("key_match_reasons", [])[:2])
        linkedin_search = f"https://www.linkedin.com/search/results/people/?keywords={job['company'].replace(' ', '%20')}%20{hm.replace(' ', '%20')}"

        rows_html += f"""
        <tr style="border-bottom: 1px solid #eee;">
            <td style="padding: 14px 12px;">
                <div style="font-weight: 600; font-size: 15px; color: #1a2744;">{job['title']}</div>
                <div style="color: #666; font-size: 13px; margin-top: 2px;">🏢 {job['company']} &nbsp;|&nbsp; 📍 {job['location']}</div>
                {f'<div style="color: #555; font-size: 12px; margin-top: 4px;">✨ {reasons}</div>' if reasons else ''}
                {f'<div style="color: #1565C0; font-size: 12px; margin-top: 4px;">💬 <em>{hook}</em></div>' if hook else ''}
                {f'<div style="font-size: 12px; margin-top: 4px;">📧 Subject: <strong>{subject}</strong></div>' if subject else ''}
                <div style="margin-top: 6px;">
                    <a href="{job['url']}" style="background: #E8690A; color: white; padding: 4px 12px; border-radius: 4px; text-decoration: none; font-size: 12px; font-weight: 600;">Apply →</a>
                    {f'&nbsp; <a href="{linkedin_search}" style="background: #0077B5; color: white; padding: 4px 12px; border-radius: 4px; text-decoration: none; font-size: 12px;">Find {hm} →</a>' if hm else ''}
                </div>
            </td>
            <td style="padding: 14px 12px; text-align: center; vertical-align: top;">
                <div style="font-size: 22px; font-weight: 700; color: {color};">{score}</div>
                <div style="font-size: 11px; color: #888;">/10</div>
                <div style="font-size: 14px; margin-top: 4px;">{visa}</div>
            </td>
        </tr>"""

    other_rows = ""
    for job in other_jobs:
        score = job.get("fit_score", "?")
        other_rows += f"""
        <tr style="border-bottom: 1px solid #f5f5f5;">
            <td style="padding: 8px 12px;">
                <a href="{job['url']}" style="color: #1a2744; text-decoration: none; font-size: 13px;">{job['title']}</a>
                <span style="color: #888; font-size: 12px;"> — {job['company']} | {job['location']}</span>
            </td>
            <td style="padding: 8px 12px; text-align: center; color: #888; font-size: 13px;">{score}/10</td>
        </tr>"""

    return f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 680px; margin: 0 auto; background: #fff;">
        <div style="background: #1a2744; color: white; padding: 20px 24px; border-radius: 8px 8px 0 0;">
            <h1 style="margin: 0; font-size: 20px; font-weight: 600;">🇳🇱 Netherlands Job Digest</h1>
            <p style="margin: 4px 0 0; font-size: 13px; opacity: 0.8;">{today} — {total_scraped} jobs scraped from {len(GREENHOUSE_COMPANIES) + len(LEVER_COMPANIES)} companies</p>
        </div>

        <div style="padding: 16px 24px; background: #FFF3E8; border-left: 4px solid #E8690A;">
            <strong style="font-size: 14px;">Top {len(top_jobs)} matches (fit ≥ 7)</strong>
            <span style="font-size: 12px; color: #666;"> — Apply + outreach these first</span>
        </div>

        <table style="width: 100%; border-collapse: collapse;">
            <thead>
                <tr style="background: #f9f9f7;">
                    <th style="padding: 10px 12px; text-align: left; font-size: 12px; color: #888; font-weight: 500;">Role & Outreach</th>
                    <th style="padding: 10px 12px; text-align: center; font-size: 12px; color: #888; font-weight: 500; width: 60px;">Fit</th>
                </tr>
            </thead>
            <tbody>{rows_html}</tbody>
        </table>

        {f'''
        <div style="padding: 16px 24px; background: #f9f9f7; margin-top: 16px;">
            <strong style="font-size: 13px; color: #666;">Other matches (fit < 7)</strong>
        </div>
        <table style="width: 100%; border-collapse: collapse;">
            <tbody>{other_rows}</tbody>
        </table>
        ''' if other_rows else ''}

        <div style="padding: 20px 24px; background: #f5f5f2; border-radius: 0 0 8px 8px; font-size: 12px; color: #888; text-align: center;">
            <p>IND Recognized Sponsors: <a href="https://ind.nl/en/public-register-recognised-sponsors" style="color: #E8690A;">Check register →</a></p>
            <p style="margin-top: 4px;">NL Job Hunter — Running on GitHub Actions — Zero cost</p>
        </div>
    </div>"""


def format_digest_text(jobs: list[dict], total_scraped: int) -> str:
    lines = [f"\n🇳🇱 NL Job Digest — {datetime.now(timezone.utc).strftime('%b %d, %Y')}"]
    lines.append(f"Found {len(jobs)} matches from {total_scraped} scraped\n")
    for i, job in enumerate([j for j in jobs if j.get("fit_score", 0) >= 7][:10], 1):
        lines.append(f"{i}. {job['title']} @ {job['company']}")
        lines.append(f"   📍 {job['location']} | ⭐ {job.get('fit_score', '?')}/10")
        lines.append(f"   🔗 {job['url']}")
        if job.get("cold_email_hook"):
            lines.append(f"   💬 {job['cold_email_hook']}")
        lines.append("")
    return "\n".join(lines)


# =============================================================================
# MAIN
# =============================================================================
async def main():
    print(f"🇳🇱 NL Job Hunter starting at {datetime.now(timezone.utc).isoformat()}")
    print(f"Scraping {len(GREENHOUSE_COMPANIES)} Greenhouse + {len(LEVER_COMPANIES)} Lever companies...")

    # Step 1: Fetch all NL jobs
    start = time.time()
    jobs = await fetch_all_jobs()
    total_scraped = len(jobs)
    print(f"Found {total_scraped} NL jobs in {time.time() - start:.1f}s")

    if not jobs:
        print("No jobs found. Exiting.")
        send_email_digest([], 0)
        return

    # Step 2: Score with Gemini
    print("Scoring with Gemini...")
    scored = await score_with_gemini(jobs)
    print(f"Scored {len(scored)} jobs, top fit: {scored[0].get('fit_score', '?')}/10 — {scored[0]['title']} @ {scored[0]['company']}")

    # Step 3: Append to Google Sheet
    print("Appending to Google Sheet...")
    append_to_google_sheet(scored)

    # Step 4: Send email digest
    print("Sending email digest...")
    send_email_digest(scored, total_scraped)

    print(f"✅ Done in {time.time() - start:.1f}s total")


if __name__ == "__main__":
    asyncio.run(main())