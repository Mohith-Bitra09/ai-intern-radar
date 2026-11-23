import os
import re
import html
from datetime import datetime, timezone, timedelta
import feedparser
import requests
from bs4 import BeautifulSoup

# Try importing JobSpy safely
try:
    from jobspy import scrape_jobs
    JOBSPY_AVAILABLE = True
except ImportError:
    JOBSPY_AVAILABLE = False
    print("[Scraper] python-jobspy not found. Falling back to public RSS feeds.")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/json, text/xml, application/xml, text/html"
}

INTERN_KEYWORDS = [
    r"\bintern\b", r"\binternship\b", r"\btrainee\b", r"\bfellow\b",
    r"\bfellowship\b", r"\bapprentice\b", r"\bapprenticeship\b"
]

AI_KEYWORDS = [
    r"\bai\b", r"\bartificial intelligence\b", r"\bmachine learning\b",
    r"\bml\b", r"\bdeep learning\b", r"\bnlp\b", r"\bnatural language\b",
    r"\bcomputer vision\b", r"\bllm\b", r"\bgenai\b", r"\bgenerative ai\b",
    r"\bdata science intern\b", r"\bdata scientist intern\b", r"\bprompt engineer\b"
]

# Pre-filter keywords for fake, pay-to-intern, or course-selling mills
SPAM_EDTECH_PATTERNS = [
    r"training program", r"registration fee", r"pay after placement",
    r"certification course", r"stipend based on performance", r"unpaid training",
    r"course fee", r"training cum internship", r"training \+ internship",
    r"internship with training", r"pay to intern", r"enrollment fee",
    r"processing fee", r"security deposit", r"guaranteed placement",
    r"placement guarantee", r"pay for certificate", r"certificate fee",
    r"pay to work", r"internship program with training"
]

# Known notorious EdTech certificate mills / spam internship providers
KNOWN_EDTECH_MILLS = [
    r"\binternpe\b", r"\boasis infobyte\b", r"\bbharat intern\b", r"\bcodealpha\b",
    r"\bletsgrowmore\b", r"\boctanet\b", r"\bsync intern\b", r"\btechnohacks\b",
    r"\bvaultofcodes\b", r"\bslash mark\b", r"\bsuven\b", r"\bcodsoft\b",
    r"\binterncareer\b", r"\bthe sparks foundation\b", r"\btutort\b",
    r"\bverzeo\b", r"\bmycaptain\b"
]

def clean_html(raw_html: str) -> str:
    """Strip HTML tags and convert to clean text."""
    if not raw_html:
        return ""
    soup = BeautifulSoup(raw_html, "html.parser")
    text = soup.get_text(separator="\n")
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()

def matches_ai_internship(title: str, description: str = "") -> bool:
    """Check if title and description match AI/ML internship criteria."""
    combined = f"{title} {description}".lower()
    title_lower = title.lower()

    # Must contain an internship keyword in title or description
    has_intern = any(re.search(pat, title_lower) for pat in INTERN_KEYWORDS) or \
                 any(re.search(pat, combined) for pat in INTERN_KEYWORDS)
    if not has_intern:
        return False

    # Must contain an AI/ML keyword
    has_ai = any(re.search(pat, title_lower) for pat in AI_KEYWORDS) or \
             any(re.search(pat, combined) for pat in AI_KEYWORDS)
    return has_ai

def is_spam_or_edtech(company: str, title: str, description: str = "") -> tuple[bool, str]:
    """
    Pre-filter check to detect and drop spam, course-selling, or pay-to-intern listings.
    Returns (is_spam, reason).
    """
    company_lower = (company or "").lower()
    title_lower = (title or "").lower()
    desc_lower = (description or "").lower()
    combined = f"{title_lower} {company_lower} {desc_lower}"

    # Check known fake training mills
    for mill in KNOWN_EDTECH_MILLS:
        if re.search(mill, company_lower) or re.search(mill, title_lower):
            return True, f"Known certificate/training mill: {company}"

    # Check spam and pay-to-intern keywords
    for pattern in SPAM_EDTECH_PATTERNS:
        if re.search(pattern, combined):
            return True, f"Matched spam/pay-to-intern indicator: '{pattern}'"

    return False, ""

def classify_and_filter_location(location: str, is_remote: bool, source: str = "") -> tuple[bool, str, str, int]:
    """
    Classifies location based on strict user priorities:
    1. Priority 1 (Highest):
       - International Remote (Global, US/Europe remote open to international interns) -> Rank 1
       - India Remote -> Rank 1
    2. Priority 2:
       - Onsite/Hybrid in Hyderabad, Bengaluru (Bangalore), Chennai -> Rank 2
    3. Drop all other cities immediately unless explicitly Remote -> Rank 999 (is_allowed = False)

    Returns: (is_allowed, priority_tag, priority_category, priority_rank)
    """
    loc_clean = (location or "").strip()
    loc_lower = loc_clean.lower()

    # 1. Check if role is Remote
    is_remote_role = (
        is_remote or
        any(term in loc_lower for term in [
            "remote", "anywhere", "worldwide", "global", "telecommute",
            "work from home", "wfh", "virtual"
        ]) or
        any(board in source.lower() for board in ["remotive", "jobicy", "weworkremotely"])
    )

    if is_remote_role:
        is_india_remote = (
            "india" in loc_lower or
            "bengaluru" in loc_lower or "bangalore" in loc_lower or
            "hyderabad" in loc_lower or "chennai" in loc_lower or
            "delhi" in loc_lower or "mumbai" in loc_lower or "pune" in loc_lower
        )
        if is_india_remote:
            return True, "🏠 India Remote", "INDIA_REMOTE", 1
        else:
            return True, "🌍 International Remote", "INTERNATIONAL_REMOTE", 1

    # 2. Check for Priority 2 Onsite/Hybrid Target Cities (Hyderabad, Bengaluru, Chennai)
    if any(b in loc_lower for b in ["bengaluru", "bangalore"]):
        return True, "📍 Bengaluru", "TARGET_CITY", 2
    if any(h in loc_lower for h in ["hyderabad", "secunderabad", "cyberabad"]):
        return True, "📍 Hyderabad", "TARGET_CITY", 2
    if any(c in loc_lower for c in ["chennai", "madras"]):
        return True, "📍 Chennai", "TARGET_CITY", 2

    # 3. Disallowed: Onsite/Hybrid in non-target cities (e.g. Pune, Mumbai, Delhi, Gurgaon, Noida, etc.)
    return False, "Non-Target Location", "DISALLOWED", 999

def parse_iso_or_rfc(date_str: str) -> datetime | None:
    """Attempt parsing multiple date formats into timezone-aware datetime."""
    if not date_str:
        return None
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        pass

    for fmt in (
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d"
    ):
        try:
            dt = datetime.strptime(date_str[:25], fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            continue
    return None

def scrape_jobspy_jobs(hours_old: int = 24) -> list[dict]:
    """Scrape AI/ML internships using python-jobspy across Indeed & Glassdoor."""
    if not JOBSPY_AVAILABLE:
        return []

    jobs = []
    # Streamlined high-speed search configs:
    # 1. India (covers Bengaluru, Hyderabad, Chennai, and India Remote)
    # 2. Remote (covers International Remote)
    configs = [
        {
            "site_name": ["indeed", "glassdoor"],
            "search_term": "Machine Learning Intern",
            "location": "India",
            "country_indeed": "india",
            "is_remote": False,
            "results_wanted": 15,
        },
        {
            "site_name": ["indeed", "glassdoor"],
            "search_term": "AI Intern",
            "location": "India",
            "country_indeed": "india",
            "is_remote": False,
            "results_wanted": 15,
        },
        {
            "site_name": ["indeed", "glassdoor"],
            "search_term": "Machine Learning Intern",
            "location": "Remote",
            "country_indeed": "usa",
            "is_remote": True,
            "results_wanted": 15,
        },
        {
            "site_name": ["indeed", "glassdoor"],
            "search_term": "AI Intern",
            "location": "Remote",
            "country_indeed": "usa",
            "is_remote": True,
            "results_wanted": 15,
        }
    ]

    for cfg in configs:
        try:
            print(f"[JobSpy] Searching: {cfg['search_term']} | Loc: {cfg.get('location')} | Remote: {cfg.get('is_remote')}")
            df = scrape_jobs(
                site_name=cfg["site_name"],
                search_term=cfg["search_term"],
                location=cfg.get("location"),
                is_remote=cfg.get("is_remote", False),
                country_indeed=cfg.get("country_indeed", "india"),
                results_wanted=cfg["results_wanted"],
                hours_old=hours_old,
                fetch_description=True,
                verbose=0
            )

            if df is None or df.empty:
                continue

            for _, row in df.iterrows():
                title = str(row.get("title", "") or "").strip()
                company = str(row.get("company", "") or "").strip()
                location = str(row.get("location", "") or "").strip()
                job_url = str(row.get("job_url", "") or "").strip()
                description = str(row.get("description", "") or "").strip()
                site = str(row.get("site", "jobspy") or "jobspy")
                is_remote = bool(row.get("is_remote", False))

                if not job_url or not title:
                    continue

                # 1. Location & Priority Filter (Drop other cities immediately)
                is_allowed, tag, category, rank = classify_and_filter_location(location, is_remote, site)
                if not is_allowed:
                    continue

                # 2. Spam / EdTech Pre-filter
                is_spam, reason = is_spam_or_edtech(company, title, description)
                if is_spam:
                    print(f"   [Pre-Filter] 🚫 Dropped training/spam listing: {company} - {title} ({reason})")
                    continue

                # Salary format
                min_amount = row.get("min_amount")
                max_amount = row.get("max_amount")
                currency = row.get("currency", "")
                interval = row.get("interval", "")
                salary_str = ""
                if min_amount and max_amount:
                    salary_str = f"{currency} {min_amount:,.0f} - {max_amount:,.0f} / {interval}".strip()
                elif min_amount:
                    salary_str = f"{currency} {min_amount:,.0f} / {interval}".strip()

                jobs.append({
                    "title": title,
                    "company": company,
                    "location": location or ("Remote" if is_remote else "Bengaluru / Hyderabad / Chennai"),
                    "apply_url": job_url,
                    "description": description[:3500],
                    "stipend": salary_str or "Not specified",
                    "date_posted": str(row.get("date_posted", "Recently")),
                    "is_remote": is_remote,
                    "priority_tag": tag,
                    "priority_category": category,
                    "priority_rank": rank,
                    "source": f"JobSpy ({site.capitalize()})"
                })
        except Exception as e:
            print(f"[JobSpy] Search error for {cfg['search_term']} in {cfg.get('location')}: {e}")

    return jobs

def scrape_remotive_jobs(hours_old: int = 24) -> list[dict]:
    """Fetch remote AI/ML internships from Remotive free API."""
    jobs = []
    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours_old)
    
    endpoints = [
        "https://remotive.com/api/remote-jobs?category=data&limit=30",
        "https://remotive.com/api/remote-jobs?search=intern&limit=30"
    ]

    for url in endpoints:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=12)
            if resp.status_code != 200:
                continue
            data = resp.json()
            job_list = data.get("jobs", [])

            for item in job_list:
                title = item.get("title", "")
                desc_html = item.get("description", "")
                desc_text = clean_html(desc_html)
                pub_date_str = item.get("publication_date", "")
                pub_date = parse_iso_or_rfc(pub_date_str)

                if pub_date and pub_date < cutoff_time:
                    continue

                if not matches_ai_internship(title, desc_text):
                    continue

                company = item.get("company_name", "Unknown")
                is_spam, reason = is_spam_or_edtech(company, title, desc_text)
                if is_spam:
                    print(f"   [Pre-Filter] 🚫 Dropped training/spam: {company} - {title} ({reason})")
                    continue

                location = item.get("candidate_required_location", "Remote Worldwide")
                is_allowed, tag, category, rank = classify_and_filter_location(location, True, "Remotive")
                if not is_allowed:
                    continue

                jobs.append({
                    "title": title,
                    "company": company,
                    "location": location,
                    "apply_url": item.get("url", ""),
                    "description": desc_text[:3500],
                    "stipend": item.get("salary", "") or "Not specified",
                    "date_posted": pub_date_str[:10] if pub_date_str else "Recently",
                    "is_remote": True,
                    "priority_tag": tag,
                    "priority_category": category,
                    "priority_rank": rank,
                    "source": "Remotive"
                })
        except Exception as e:
            print(f"[Remotive] Error fetching jobs: {e}")

    return jobs

def scrape_jobicy_jobs(hours_old: int = 24) -> list[dict]:
    """Fetch remote AI/ML internships from Jobicy free API."""
    jobs = []
    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours_old)
    
    tags = ["ai", "machine-learning", "data-science", "intern"]
    for tag in tags:
        try:
            url = f"https://jobicy.com/api/v2/remote-jobs?count=20&tag={tag}"
            resp = requests.get(url, headers=HEADERS, timeout=12)
            if resp.status_code != 200:
                continue
            data = resp.json()
            job_list = data.get("jobs", [])

            for item in job_list:
                title = item.get("jobTitle", "")
                desc_html = item.get("jobDescription", "")
                desc_text = clean_html(desc_html)
                pub_date_str = item.get("pubDate", "")
                pub_date = parse_iso_or_rfc(pub_date_str)

                if pub_date and pub_date < cutoff_time:
                    continue

                if not matches_ai_internship(title, desc_text):
                    continue

                company = item.get("companyName", "Unknown")
                is_spam, reason = is_spam_or_edtech(company, title, desc_text)
                if is_spam:
                    print(f"   [Pre-Filter] 🚫 Dropped training/spam: {company} - {title} ({reason})")
                    continue

                location = item.get("jobGeo", "Remote")
                is_allowed, tag, category, rank = classify_and_filter_location(location, True, "Jobicy")
                if not is_allowed:
                    continue

                salary_str = ""
                min_sal = item.get("annualSalaryMin")
                max_sal = item.get("annualSalaryMax")
                currency = item.get("salaryCurrency", "USD")
                if min_sal and max_sal:
                    salary_str = f"{currency} {min_sal} - {max_sal}"
                elif min_sal:
                    salary_str = f"{currency} {min_sal}"

                jobs.append({
                    "title": title,
                    "company": company,
                    "location": location,
                    "apply_url": item.get("url", ""),
                    "description": desc_text[:3500],
                    "stipend": salary_str or "Not specified",
                    "date_posted": pub_date_str[:10] if pub_date_str else "Recently",
                    "is_remote": True,
                    "priority_tag": tag,
                    "priority_category": category,
                    "priority_rank": rank,
                    "source": "Jobicy"
                })
        except Exception as e:
            print(f"[Jobicy] Error with tag {tag}: {e}")

    return jobs

def scrape_weworkremotely_rss(hours_old: int = 24) -> list[dict]:
    """Fetch AI/ML internships from WeWorkRemotely RSS feeds."""
    feeds = [
        "https://weworkremotely.com/categories/remote-programming-jobs.rss",
        "https://weworkremotely.com/categories/remote-data-science-jobs.rss"
    ]
    jobs = []
    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours_old)

    for feed_url in feeds:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                title = entry.get("title", "")
                link = entry.get("link", "")
                summary_html = entry.get("summary", "")
                summary_text = clean_html(summary_html)
                published_parsed = entry.get("published_parsed")

                if published_parsed:
                    pub_dt = datetime(*published_parsed[:6], tzinfo=timezone.utc)
                    if pub_dt < cutoff_time:
                        continue
                else:
                    pub_dt = None

                if not matches_ai_internship(title, summary_text):
                    continue

                company = "Unknown"
                role_title = title
                if ":" in title:
                    parts = title.split(":", 1)
                    company = parts[0].strip()
                    role_title = parts[1].strip()

                is_spam, reason = is_spam_or_edtech(company, role_title, summary_text)
                if is_spam:
                    print(f"   [Pre-Filter] 🚫 Dropped training/spam: {company} - {role_title} ({reason})")
                    continue

                is_allowed, tag, category, rank = classify_and_filter_location("Remote Worldwide", True, "WeWorkRemotely")
                if not is_allowed:
                    continue

                jobs.append({
                    "title": role_title,
                    "company": company,
                    "location": "Remote Worldwide",
                    "apply_url": link,
                    "description": summary_text[:3500],
                    "stipend": "Not specified",
                    "date_posted": pub_dt.strftime("%Y-%m-%d") if pub_dt else "Recently",
                    "is_remote": True,
                    "priority_tag": tag,
                    "priority_category": category,
                    "priority_rank": rank,
                    "source": "WeWorkRemotely"
                })
        except Exception as e:
            print(f"[WWR RSS] Error parsing {feed_url}: {e}")

    return jobs

def fetch_all_ai_internships(hours_old: int = 24) -> list[dict]:
    """
    Aggregate AI/ML internships from python-jobspy and public feeds posted in the last 24 hours.
    Prioritizes:
    - Priority 1: Remote India & International Remote
    - Priority 2: Hyderabad, Bengaluru, Chennai
    Filters out spam, fake EdTech certificate mills, and non-target locations.
    """
    all_jobs = []

    print("[Scraper] 1/4 Fetching from JobSpy (Indeed, Glassdoor)...")
    jobspy_jobs = scrape_jobspy_jobs(hours_old=hours_old)
    print(f"[Scraper] JobSpy found: {len(jobspy_jobs)} candidate jobs matching target criteria.")
    all_jobs.extend(jobspy_jobs)

    print("[Scraper] 2/4 Fetching from Remotive public API...")
    remotive_jobs = scrape_remotive_jobs(hours_old=hours_old)
    print(f"[Scraper] Remotive found: {len(remotive_jobs)} candidate jobs.")
    all_jobs.extend(remotive_jobs)

    print("[Scraper] 3/4 Fetching from Jobicy public API...")
    jobicy_jobs = scrape_jobicy_jobs(hours_old=hours_old)
    print(f"[Scraper] Jobicy found: {len(jobicy_jobs)} candidate jobs.")
    all_jobs.extend(jobicy_jobs)

    print("[Scraper] 4/4 Fetching from WeWorkRemotely RSS feeds...")
    wwr_jobs = scrape_weworkremotely_rss(hours_old=hours_old)
    print(f"[Scraper] WWR found: {len(wwr_jobs)} candidate jobs.")
    all_jobs.extend(wwr_jobs)

    # In-memory deduplication by URL or (company + title)
    unique_jobs = []
    seen_in_batch = set()

    for j in all_jobs:
        url = (j.get("apply_url") or "").strip().lower()
        key = f"{j.get('company','').lower()}::{j.get('title','').lower()}"
        if url and url in seen_in_batch:
            continue
        if key in seen_in_batch:
            continue
        
        if url:
            seen_in_batch.add(url)
        seen_in_batch.add(key)
        unique_jobs.append(j)

    print(f"[Scraper] Total verified candidate jobs matching location & pre-filter: {len(unique_jobs)}")
    return unique_jobs
