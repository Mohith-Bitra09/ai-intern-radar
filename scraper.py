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

def clean_html(raw_html: str) -> str:
    """Strip HTML tags and convert to clean text."""
    if not raw_html:
        return ""
    soup = BeautifulSoup(raw_html, "html.parser")
    text = soup.get_text(separator="\n")
    # clean extra whitespace
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

def is_india_or_remote(location: str, is_remote_flag: bool = False) -> bool:
    """Check if location is in India or remote."""
    if is_remote_flag:
        return True
    if not location:
        return True # Default to allow if unspecified
    loc_lower = location.lower()
    india_indicators = [
        "india", "bangalore", "bengaluru", "hyderabad", "pune", "mumbai",
        "delhi", "gurgaon", "gurugram", "noida", "chennai", "kolkata",
        "ahmedabad", "kerala", "kochi", "coimbatore"
    ]
    remote_indicators = ["remote", "anywhere", "worldwide", "global", "telecommute", "work from home", "wfh"]
    
    return any(ind in loc_lower for ind in india_indicators) or any(ind in loc_lower for ind in remote_indicators)

def parse_iso_or_rfc(date_str: str) -> datetime | None:
    """Attempt parsing multiple date formats into timezone-aware datetime."""
    if not date_str:
        return None
    try:
        # e.g., '2026-11-22T08:00:00Z' or with offset
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        pass

    # Try common formats
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
    """Scrape AI/ML internships using python-jobspy across LinkedIn, Indeed, Glassdoor, and Google."""
    if not JOBSPY_AVAILABLE:
        return []

    jobs = []
    # Search configurations:
    # 1. India specific AI & ML internships
    # 2. Remote AI & ML internships
    configs = [
        {
            "site_name": ["linkedin", "indeed", "glassdoor", "google"],
            "search_term": "Machine Learning Intern",
            "location": "India",
            "country_indeed": "india",
            "is_remote": False,
            "results_wanted": 10,
        },
        {
            "site_name": ["linkedin", "indeed", "glassdoor", "google"],
            "search_term": "AI Intern",
            "location": "India",
            "country_indeed": "india",
            "is_remote": False,
            "results_wanted": 10,
        },
        {
            "site_name": ["linkedin", "indeed", "glassdoor", "google"],
            "search_term": "Machine Learning Intern",
            "location": "Remote",
            "country_indeed": "usa",
            "is_remote": True,
            "results_wanted": 10,
        },
        {
            "site_name": ["linkedin", "indeed", "glassdoor", "google"],
            "search_term": "AI Intern",
            "location": "Remote",
            "country_indeed": "usa",
            "is_remote": True,
            "results_wanted": 10,
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
                country_indeed=cfg.get("country_indeed", "usa"),
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

                if not is_india_or_remote(location, is_remote):
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
                    "location": location or ("Remote" if is_remote else "India / Remote"),
                    "apply_url": job_url,
                    "description": description[:3500], # Keep concise for LLM context
                    "stipend": salary_str or "Not specified",
                    "date_posted": str(row.get("date_posted", "Recently")),
                    "is_remote": is_remote,
                    "source": f"JobSpy ({site.capitalize()})"
                })
        except Exception as e:
            print(f"[JobSpy] Search failed for {cfg['search_term']}: {e}")

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

                # Filter within timeframe if date is available
                if pub_date and pub_date < cutoff_time:
                    continue

                if not matches_ai_internship(title, desc_text):
                    continue

                location = item.get("candidate_required_location", "Remote Worldwide")
                if not is_india_or_remote(location, True):
                    continue

                jobs.append({
                    "title": title,
                    "company": item.get("company_name", "Unknown"),
                    "location": location,
                    "apply_url": item.get("url", ""),
                    "description": desc_text[:3500],
                    "stipend": item.get("salary", "") or "Not specified",
                    "date_posted": pub_date_str[:10] if pub_date_str else "Recently",
                    "is_remote": True,
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

                location = item.get("jobGeo", "Remote")
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
                    "company": item.get("companyName", "Unknown"),
                    "location": location,
                    "apply_url": item.get("url", ""),
                    "description": desc_text[:3500],
                    "stipend": salary_str or "Not specified",
                    "date_posted": pub_date_str[:10] if pub_date_str else "Recently",
                    "is_remote": True,
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

                # WWR titles usually look like "Company: Role"
                company = "Unknown"
                role_title = title
                if ":" in title:
                    parts = title.split(":", 1)
                    company = parts[0].strip()
                    role_title = parts[1].strip()

                jobs.append({
                    "title": role_title,
                    "company": company,
                    "location": "Remote",
                    "apply_url": link,
                    "description": summary_text[:3500],
                    "stipend": "Not specified",
                    "date_posted": pub_dt.strftime("%Y-%m-%d") if pub_dt else "Recently",
                    "is_remote": True,
                    "source": "WeWorkRemotely"
                })
        except Exception as e:
            print(f"[WWR RSS] Error parsing {feed_url}: {e}")

    return jobs

def fetch_all_ai_internships(hours_old: int = 24) -> list[dict]:
    """
    Aggregate AI/ML internships from python-jobspy and public feeds posted in the last 24 hours.
    Deduplicates within the current batch.
    """
    all_jobs = []

    print("[Scraper] 1/4 Fetching from JobSpy (LinkedIn, Indeed, Glassdoor, Google)...")
    jobspy_jobs = scrape_jobspy_jobs(hours_old=hours_old)
    print(f"[Scraper] JobSpy found: {len(jobspy_jobs)} candidate jobs.")
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

    print(f"[Scraper] Total unique candidate jobs collected: {len(unique_jobs)}")
    return unique_jobs
