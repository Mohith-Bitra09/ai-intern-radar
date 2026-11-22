import json
import os
import re
from datetime import datetime, timezone
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

DEFAULT_SEEN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seen_jobs.json")

# Query parameters commonly used for tracking that can be stripped
TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "refId", "trackingId", "trk", "ref", "position", "pageNum", "origin",
    "source", "context", "originalSubdomain", "fbclid", "gclid"
}

def normalize_url(url: str) -> str:
    """Normalize a job URL to prevent duplicates due to tracking parameters or casing."""
    if not url:
        return ""
    url = url.strip()
    try:
        parsed = urlparse(url)
        scheme = parsed.scheme.lower() or "https"
        netloc = parsed.netloc.lower()
        path = parsed.path.rstrip("/")
        if not path:
            path = "/"
        
        # Filter tracking parameters
        query_pairs = parse_qsl(parsed.query, keep_blank_values=False)
        clean_pairs = [(k, v) for k, v in query_pairs if k not in TRACKING_PARAMS]
        clean_pairs.sort() # Ensure deterministic order
        clean_query = urlencode(clean_pairs)

        return urlunparse((scheme, netloc, path, parsed.params, clean_query, ""))
    except Exception:
        return url.strip().lower()

class SeenJobsTracker:
    def __init__(self, filepath: str = DEFAULT_SEEN_FILE):
        self.filepath = filepath
        self.seen_urls: set[str] = set()
        self.load()

    def load(self):
        """Load seen URLs from JSON file."""
        if not os.path.exists(self.filepath):
            self.seen_urls = set()
            return

        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                urls = data.get("seen_urls", [])
                self.seen_urls = {normalize_url(u) for u in urls if u}
        except Exception as e:
            print(f"[Tracker] Warning loading {self.filepath}: {e}. Initializing empty set.")
            self.seen_urls = set()

    def is_seen(self, url: str) -> bool:
        """Check if normalized URL is already seen."""
        norm = normalize_url(url)
        return norm in self.seen_urls

    def add(self, url: str):
        """Mark URL as seen."""
        norm = normalize_url(url)
        if norm:
            self.seen_urls.add(norm)

    def save(self):
        """Save seen URLs to JSON file."""
        data = {
            "seen_urls": sorted(list(self.seen_urls)),
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "count": len(self.seen_urls)
        }
        try:
            temp_file = f"{self.filepath}.tmp"
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(temp_file, self.filepath)
        except Exception as e:
            print(f"[Tracker] Error saving {self.filepath}: {e}")
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
