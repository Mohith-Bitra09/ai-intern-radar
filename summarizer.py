import os
import html
from google import genai
from google.genai import types

# Candidate models in preferred order (supporting both current and legacy flash versions)
PREFERRED_MODELS = [
    "gemini-3.5-flash",
    "gemini-3.8-flash",
    "gemini-2.5-flash",
    "gemini-3.1-flash-lite"
]

class JobSummarizer:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is not set. Please set it in your .env file.")
        
        self.client = genai.Client(api_key=self.api_key)

    def summarize_job(self, job_data: dict) -> str:
        """
        Summarizes job posting into a Telegram-ready HTML format using Gemini Flash.
        Fields:
        - Company Name
        - Role
        - Location
        - Eligibility & Required Skills
        - Stipend (if listed)
        - Step-by-step Application Instructions
        - Direct Apply Link
        """
        title = job_data.get("title", "AI/ML Internship")
        company = job_data.get("company", "Not Specified")
        location = job_data.get("location", "India / Remote")
        raw_stipend = job_data.get("stipend", "Not specified")
        apply_url = job_data.get("apply_url", "")
        source = job_data.get("source", "Job Board")
        description = job_data.get("description", "No detailed description provided.")

        prompt = f"""
You are an expert career intelligence AI assistant. Analyze the following job posting and create a clean, high-impact Telegram alert for students and developers seeking AI/ML internships.

Target Format:
Use Telegram HTML formatting strictly (only <b>, <i>, <code>, <a href="...">).
Do NOT wrap your entire response in markdown code blocks like ```html. Return the raw message text directly.

You MUST extract and format these exact sections:
1. Header: 🚀 <b>NEW AI/ML INTERNSHIP ALERT</b>
2. 🏢 <b>Company Name:</b> [Company Name]
3. 💼 <b>Role:</b> [Job Title / Position]
4. 📍 <b>Location:</b> [Location e.g. Bengaluru, India / Remote Worldwide]
5. 💰 <b>Stipend / Compensation:</b> [Stipend/Salary if mentioned or infer from text, otherwise "Not explicitly disclosed in posting"]
6. 🎓 <b>Eligibility & Required Skills:</b>
   • Bullet points of degrees/year of study (if mentioned), key tech stack (e.g. Python, PyTorch, LangChain, Transformers, SQL, etc.)
7. 📝 <b>Step-by-step Application Instructions:</b>
   1. Specific actionable application step (e.g., Prepare resume highlighting ML projects)
   2. How to submit (portal, form, email, or direct button)
   3. Tips on standing out for this specific role
8. 🔗 <b>Direct Apply Link:</b> <a href="{apply_url}">Click Here to Apply on {source}</a>

Job Information:
- Title: {title}
- Company: {company}
- Location: {location}
- Provided Salary/Stipend: {raw_stipend}
- Apply Link: {apply_url}
- Platform Source: {source}

Job Description:
{description}

Ensure any raw HTML entities like '&' are properly escaped as '&amp;', '<' as '&lt;', and '>' as '&gt;' unless they are valid Telegram HTML tags (<b>, </b>, <i>, </i>, <code>, </code>, <a href="...">, </a>). Keep it engaging, professional, and easy to read on mobile.
"""
        response_text = None
        for model_name in PREFERRED_MODELS:
            try:
                response = self.client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.2,
                    )
                )
                if response and response.text:
                    response_text = response.text.strip()
                    break
            except Exception as e:
                # If deprecated or temporary capacity spike, failover to next model
                continue

        if response_text:
            text = response_text
            # Remove any wrapping ```html or ``` if Gemini added it
            if text.startswith("```"):
                lines = text.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                text = "\n".join(lines).strip()
            
            # Ensure apply link is present
            if apply_url and apply_url not in text:
                text += f"\n\n🔗 <b>Direct Apply Link:</b> <a href=\"{apply_url}\">Apply Here</a>"
            
            return text

        # Resilient fallback formatted template if all model calls fail
        fallback = f"""🚀 <b>NEW AI/ML INTERNSHIP ALERT</b>

🏢 <b>Company Name:</b> {html.escape(company)}
💼 <b>Role:</b> {html.escape(title)}
📍 <b>Location:</b> {html.escape(location)}
💰 <b>Stipend / Compensation:</b> {html.escape(raw_stipend)}

🎓 <b>Eligibility & Required Skills:</b>
• Relevant background in Computer Science, Artificial Intelligence, or Data Science
• Proficiency in Python, Machine Learning fundamentals, and Deep Learning libraries

📝 <b>Step-by-step Application Instructions:</b>
1. Tailor your resume highlighting AI/ML and GenAI projects.
2. Click the apply link below to access the official job posting.
3. Complete the application form and submit promptly.

🔗 <b>Direct Apply Link:</b> <a href="{apply_url}">Click Here to Apply ({source})</a>
"""
        return fallback
