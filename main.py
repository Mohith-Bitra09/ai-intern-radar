import os
import sys
import time
import argparse
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from storage import SeenJobsTracker, normalize_url
from scraper import fetch_all_ai_internships
from summarizer import JobSummarizer
from telegram_notifier import TelegramNotifier

def check_environment() -> tuple[bool, str]:
    """Validate required environment variables."""
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

    missing = []
    if not gemini_key or "your_gemini" in gemini_key:
        missing.append("GEMINI_API_KEY")
    if not bot_token or "your_telegram_bot" in bot_token:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not chat_id or "your_telegram_chat" in chat_id:
        missing.append("TELEGRAM_CHAT_ID")

    if missing:
        err_msg = (
            f"Missing or default placeholders detected for: {', '.join(missing)}.\n"
            f"Please update your `.env` file with your real keys before running."
        )
        return False, err_msg
    return True, ""

def run_agent(hours_old: int = 24, max_alerts: int = 10, dry_run: bool = False, test_mode: bool = False):
    """Main execution loop for AI Intern Radar."""
    print("=" * 65)
    print("🛰️  AI INTERN RADAR - Automated Job Intelligence Agent")
    print("=" * 65)

    is_valid, err_msg = check_environment()
    if not is_valid:
        print(f"\n❌ Configuration Error:\n{err_msg}\n")
        sys.exit(1)

    tracker = SeenJobsTracker()
    print(f"[Storage] Loaded {len(tracker.seen_urls)} previously seen job URLs from seen_jobs.json.")

    notifier = TelegramNotifier()
    summarizer = JobSummarizer()

    if test_mode:
        print("\n[Test Mode] Sending handshake test message to Telegram...")
        success = notifier.send_test_message()
        if success:
            print("✅ Test message successfully delivered to Telegram!")
        else:
            print("❌ Failed to send test message. Check your Bot Token and Chat ID.")
        return

    # Fetch jobs
    print(f"\n[Scraper] Searching for AI/ML internships posted in the last {hours_old} hours (India & Remote)...")
    candidate_jobs = fetch_all_ai_internships(hours_old=hours_old)
    print(f"[Scraper] Discovered {len(candidate_jobs)} total candidate internships.")

    # Filter unseen jobs
    new_jobs = []
    for job in candidate_jobs:
        apply_url = job.get("apply_url", "")
        if not apply_url:
            continue
        if not tracker.is_seen(apply_url):
            new_jobs.append(job)

    print(f"[Filter] {len(new_jobs)} new unseen jobs found (ignoring {len(candidate_jobs) - len(new_jobs)} duplicates).")

    if not new_jobs:
        print("\n✨ All current jobs have already been seen or no new postings in the last 24h. Up to date!")
        return

    # Limit jobs per run to prevent flood
    jobs_to_process = new_jobs[:max_alerts]
    print(f"[Processing] Preparing alerts for {len(jobs_to_process)} new postings (limit: {max_alerts})...\n")

    sent_count = 0
    for idx, job in enumerate(jobs_to_process, 1):
        company = job.get("company", "Unknown")
        title = job.get("title", "AI/ML Intern")
        apply_url = job.get("apply_url")
        print(f"[{idx}/{len(jobs_to_process)}] Summarizing with Gemini 2.5 Flash: {company} - {title}...")

        # Generate summary using gemini-2.5-flash
        try:
            summary_message = summarizer.summarize_job(job)
        except Exception as e:
            print(f"   ⚠️ Gemini summarization error: {e}")
            continue

        if dry_run:
            print(f"\n--- [DRY RUN - Message Preview] ---")
            print(summary_message)
            print("------------------------------------\n")
            tracker.add(apply_url)
            sent_count += 1
            continue

        # Send alert to Telegram
        print(f"   📤 Sending alert to Telegram...")
        delivered = notifier.send_message(summary_message)
        if delivered:
            print(f"   ✅ Alert delivered for {company} - {title}")
            tracker.add(apply_url)
            tracker.save()
            sent_count += 1
        else:
            print(f"   ❌ Failed to send alert to Telegram.")

        # Rate limiting delay between messages
        time.sleep(1.5)

    tracker.save()
    print("\n" + "=" * 65)
    print(f"🏁 Run complete: {sent_count} alerts sent to Telegram. seen_jobs.json updated.")
    print("=" * 65)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI & Machine Learning Internship Radar Agent")
    parser.add_argument("--hours", type=int, default=24, help="Lookback window in hours (default: 24)")
    parser.add_argument("--limit", type=int, default=10, help="Maximum new jobs to alert per run (default: 10)")
    parser.add_argument("--dry-run", action="store_true", help="Print summaries without sending to Telegram")
    parser.add_argument("--test", action="store_true", help="Send a test message to verify Telegram bot connection")
    parser.add_argument("--test-live-alert", action="store_true", help="Fetch and send 1 real live alert immediately")

    args = parser.parse_args()

    if args.test_live_alert:
        run_agent(hours_old=args.hours, max_alerts=1, dry_run=False, test_mode=False)
    elif args.test:
        run_agent(test_mode=True)
    else:
        run_agent(hours_old=args.hours, max_alerts=args.limit, dry_run=args.dry_run)
