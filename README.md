# 🛰️ AI Intern Radar

An automated Python intelligence agent that tracks new **AI and Machine Learning internships** across **India** and **Remote** roles posted in the last 24 hours. It leverages **Google Gemini 2.5 Flash** (`google-genai` SDK) to analyze and distill each listing into actionable, structured alerts delivered straight to your **Telegram**.

---

## ⚡ Features

- **Zero-Cost Scraping & Discovery**: Uses `python-jobspy` (LinkedIn, Indeed, Glassdoor, Google Jobs) and public free job feeds (Remotive, Jobicy, WeWorkRemotely RSS) with 0 paid API costs.
- **AI-Powered Analysis**: Summarizes each posting using **Gemini 2.5 Flash** into:
  - 🏢 Company Name
  - 💼 Role Title
  - 📍 Location (India / Remote)
  - 💰 Stipend / Compensation
  - 🎓 Eligibility & Required Skills
  - 📝 Step-by-step Application Instructions
  - 🔗 Direct Apply Link
- **Duplicate Prevention**: Tracks seen postings in `seen_jobs.json` with URL parameter normalization.
- **Telegram Bot Delivery**: Sends clean, rich HTML alerts with mobile-friendly links and fallback error recovery.
- **GitHub Actions Automation**: Automatically runs every 6 hours via `.github/workflows/run_agent.yml` and updates `seen_jobs.json`.

---

## 🚀 Quick Setup

### 1. Configure Credentials (`.env`)
Copy the template or edit `.env`:
```bash
GEMINI_API_KEY=your_gemini_api_key_here
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
TELEGRAM_CHAT_ID=your_telegram_chat_id_here
```

#### How to get the keys:
1. **`GEMINI_API_KEY`**: Get a free API key from [Google AI Studio](https://aistudio.google.com/app/apikey).
2. **`TELEGRAM_BOT_TOKEN`**:
   - Open Telegram and message [@BotFather](https://t.me/BotFather).
   - Send `/newbot` and follow instructions to name your bot and get the bot token.
   - **Important**: Send `/start` to your bot in Telegram so it can message you!
3. **`TELEGRAM_CHAT_ID`**:
   - Message [@userinfobot](https://t.me/userinfobot) on Telegram to see your numeric Chat ID (e.g., `123456789`).

---

## 🛠️ Usage

### Run Full Radar Agent (Default 24 Hours Lookback):
```bash
python main.py
```

### Test Telegram Bot Connection:
```bash
python main.py --test
```

### Test Live Alert (Fetch & Send 1 Real Alert Immediately):
```bash
python main.py --test-live-alert
```

### Dry Run (Preview Gemini Summaries in Terminal without sending to Telegram):
```bash
python main.py --dry-run
```

---

## 🤖 GitHub Actions Setup (Automated Runs Every 6 Hours)

To have GitHub run this automatically:
1. Push this repository to GitHub.
2. In your repo, go to **Settings** → **Secrets and variables** → **Actions**.
3. Click **New repository secret** and add:
   - `GEMINI_API_KEY`
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
4. In **Settings** → **Actions** → **General** → **Workflow permissions**, select **"Read and write permissions"** so GitHub Actions can commit the updated `seen_jobs.json`.
5. The workflow will automatically trigger every 6 hours, or you can manually trigger it anytime under the **Actions** tab.
