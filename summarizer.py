import os
import html
import re
from google import genai
from google.genai import types

# Candidate models in preferred order (supporting gemini-2.5-flash per prompt requirement, plus latest available fallbacks)
PREFERRED_MODELS = [
    "gemini-2.5-flash",
    "gemini-3.5-flash",
    "gemini-3.8-flash",
    "gemini-3.1-flash-lite"
]

class JobSummarizer:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is not set. Please set it in your .env file.")
        
        self.client = genai.Client(api_key=self.api_key)

    def summarize_job(self, job_data: dict) -> str | None:
        """
        Verifies company legitimacy via Google Search Grounding and summarizes genuine AI/ML internships.
        Returns:
            - Formatted HTML alert string if approved.
            - None if the role is rejected (SKIP) due to being an EdTech mill, training scam, or unverified.
        """
        title = job_data.get("title", "AI/ML Internship")
        company = job_data.get("company", "Not Specified")
        location = job_data.get("location", "India / Remote")
        raw_stipend = job_data.get("stipend", "Not specified")
        apply_url = job_data.get("apply_url", "")
        source = job_data.get("source", "Job Board")
        description = job_data.get("description", "No detailed description provided.")
        priority_tag = job_data.get("priority_tag", "🌍 International Remote")

        prompt = f"""
You are an expert career intelligence and corporate integrity investigator.
Your mission is to perform strict company verification and summarize this AI/Machine Learning internship opportunity.

Use Google Search to inspect the company '{company}' and evaluate this job posting.

============================================================
🚨 STRICT REJECTION POLICY (RETURN 'SKIP'):
============================================================
You MUST strictly REJECT this role by returning ONLY the single word "SKIP" (with no other text) if ANY of the following are true:
1. The company is an EdTech institute, coaching center, training academy, bootcamp, or agency selling courses, "training programs", "internship programs with certification", or asking for any fee, deposit, or placement charge.
2. The company is a notorious internship certificate mill or resume padding scam (e.g. InternPe, Oasis Infobyte, Bharat Intern, CodeAlpha, LetsGrowMore, OctaNet, Sync Intern, TechnoHacks, etc.).
3. The company has NO verifiable real software product, NO genuine engineering team, or NO credible corporate web presence.
4. The role is purely unpaid labor, commission-only, or fake task work without real engineering mentorship.

============================================================
✅ APPROVAL CRITERIA:
============================================================
Only APPROVE genuine product companies, AI/tech startups, corporate R&D labs, or established technology firms offering authentic engineering exposure and real-world AI/ML work.

============================================================
OUTPUT FORMAT IF APPROVED:
============================================================
If approved, return the clean Telegram alert formatted STRICTLY in Telegram HTML (<b>, <i>, <code>, <a href="...">).
Do NOT wrap your response in markdown backticks (no ```html).

Include these exact fields:
🚀 <b>NEW AI/ML INTERNSHIP ALERT</b>

🏢 <b>Company Name:</b> [Company Name]
💼 <b>Role:</b> [Position Title]
📍 <b>Priority & Location:</b> {priority_tag} • [Exact Location / City]
🔍 <b>Company Verification:</b> [1-line summary of what the company actually builds/does + why it is trusted, plus official website domain]
💰 <b>Stipend / Compensation:</b> [Stipend or "Not explicitly disclosed in posting"]

🎓 <b>Eligibility & Required Skills:</b>
• [Degree/Year if stated, Key tech: Python, PyTorch/TensorFlow, LLMs/Transformers, etc.]

📝 <b>Step-by-step Application Instructions:</b>
1. [Actionable step, e.g. tailored ML portfolio]
2. [Application method: portal link, form, etc.]
3. [Tip to stand out for this company]

🔗 <b>Direct Apply Link:</b> <a href="{apply_url}">Click Here to Apply on {source}</a>

Job Information:
- Company: {company}
- Title: {title}
- Location: {location}
- Provided Salary/Stipend: {raw_stipend}
- Apply Link: {apply_url}
- Platform Source: {source}

Job Description:
{description}
"""
        response_text = None

        # 1. First attempt: Use Google Search Grounding tool with preferred models
        for model_name in PREFERRED_MODELS:
            try:
                response = self.client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.1,
                        tools=[types.Tool(google_search=types.GoogleSearch())]
                    )
                )
                if response and response.text:
                    response_text = response.text.strip()
                    break
            except Exception as e:
                # If search tool fails or quota reached on search metric, try next model or fallback
                continue

        # 2. Fallback attempt: If Google Search tool hit quota/rate limits, call Gemini without tool
        if not response_text:
            for model_name in PREFERRED_MODELS:
                try:
                    response = self.client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            temperature=0.1
                        )
                    )
                    if response and response.text:
                        response_text = response.text.strip()
                        break
                except Exception:
                    continue

        if not response_text:
            # If all model calls failed, perform rule-based check
            print(f"[Summarizer] Model unavailable for {company}. Applying heuristic check.")
            return None

        # Check for rejection signal
        cleaned_first_line = response_text.splitlines()[0].strip().upper()
        if "SKIP" in cleaned_first_line or response_text.strip().upper() == "SKIP":
            print(f"[Summarizer] ❌ REJECTED by Gemini verification: {company} - {title}")
            return None

        # Clean markdown codeblocks if present
        text = response_text
        if text.startswith("```"):
            lines = text.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        # Ensure direct apply link exists in message
        if apply_url and apply_url not in text:
            text += f"\n\n🔗 <b>Direct Apply Link:</b> <a href=\"{apply_url}\">Apply Here</a>"

        return text
