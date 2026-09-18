import os
import re
import time
import base64
from html import unescape
from email.utils import parsedate_to_datetime
from typing import Optional

from dotenv import load_dotenv

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field


load_dotenv()


# ============================================================
# CONFIGURATION
# ============================================================

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

CREDENTIALS_FILE = os.getenv(
    "GMAIL_CREDENTIALS_FILE",
    "gmail_credentials.json"
)

TOKEN_FILE = os.getenv(
    "GMAIL_TOKEN_FILE",
    "gmail_token.json"
)

LOOKBACK_DAYS = int(os.getenv("GMAIL_LOOKBACK_DAYS", "7"))
MAX_EMAILS = int(os.getenv("GMAIL_MAX_RESULTS", "20"))
CACHE_SECONDS = int(os.getenv("GMAIL_CACHE_SECONDS", "600"))

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")


# ============================================================
# CACHE
# ============================================================

_cached_summary: Optional[str] = None
_cached_at: float = 0


# ============================================================
# GEMINI OUTPUT
# ============================================================

class InboxAIOutput(BaseModel):
    summary: str = Field(
        description="A concise summary of relevant plant-care emails."
    )


# ============================================================
# GMAIL AUTHENTICATION
# ============================================================

def get_gmail_service():
    """
    Authenticate with Gmail.

    First run:
        Opens browser for Google OAuth authorization.

    Later runs:
        Uses gmail_token.json and refreshes the access token
        automatically when necessary.

    This means the VM can use the saved token without
    opening a browser every time.
    """

    creds = None

    if os.path.exists(TOKEN_FILE):
        try:
            creds = Credentials.from_authorized_user_file(
                TOKEN_FILE,
                SCOPES
            )
        except Exception:
            creds = None

    if not creds or not creds.valid:

        if creds and creds.expired and creds.refresh_token:
            print("🔄 Refreshing Gmail access token...")
            creds.refresh(Request())

        else:
            if not os.path.exists(CREDENTIALS_FILE):
                raise FileNotFoundError(
                    f"Gmail credentials file not found: "
                    f"{CREDENTIALS_FILE}"
                )

            print("🌐 Opening Google OAuth authorization...")

            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_FILE,
                SCOPES
            )

            creds = flow.run_local_server(
                port=0,
                access_type="offline",
                prompt="consent"
            )

        with open(TOKEN_FILE, "w", encoding="utf-8") as token:
            token.write(creds.to_json())

        print(f"🔐 Gmail authorization saved to {TOKEN_FILE}")

    return build(
        "gmail",
        "v1",
        credentials=creds
    )


# ============================================================
# EMAIL TEXT EXTRACTION
# ============================================================

def clean_html(text: str) -> str:
    """
    Convert basic HTML email content into readable text.
    """

    text = re.sub(r"<style.*?>.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<script.*?>.*?</script>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</p\s*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)

    text = unescape(text)

    text = re.sub(r"\s+", " ", text)

    return text.strip()


def decode_body(data: str) -> str:
    """
    Decode Gmail's base64url encoded message body.
    """

    try:
        decoded = base64.urlsafe_b64decode(
            data.encode("UTF-8")
        )

        return decoded.decode(
            "utf-8",
            errors="ignore"
        )

    except Exception:
        return ""


def extract_message_text(payload: dict) -> str:
    """
    Extract readable text from Gmail message payload.
    """

    parts = payload.get("parts", [])

    if not parts:
        body = payload.get("body", {})
        data = body.get("data")

        if data:
            text = decode_body(data)

            if payload.get("mimeType") == "text/html":
                return clean_html(text)

            return text

        return ""

    plain_parts = []
    html_parts = []

    for part in parts:

        mime_type = part.get("mimeType", "")

        body = part.get("body", {})
        data = body.get("data")

        if data:
            text = decode_body(data)

            if mime_type == "text/plain":
                plain_parts.append(text)

            elif mime_type == "text/html":
                html_parts.append(clean_html(text))

        if part.get("parts"):
            nested = extract_message_text(part)

            if nested:
                plain_parts.append(nested)

    if plain_parts:
        return "\n".join(plain_parts)

    if html_parts:
        return "\n".join(html_parts)

    return ""


# ============================================================
# EMAIL HEADER HELPERS
# ============================================================

def get_header(headers: list, name: str) -> str:
    """
    Get a Gmail message header.
    """

    name = name.lower()

    for header in headers:

        if header.get("name", "").lower() == name:
            return header.get("value", "")

    return ""


# ============================================================
# DETERMINISTIC RELEVANCE FILTER
# ============================================================

HIGH_PRIORITY_TERMS = {
    "plant": 3,
    "tomato": 3,
    "gardening": 3,
    "garden": 2,
    "watering": 3,
    "water": 2,
    "soil": 3,
    "fertilizer": 3,
    "fertiliser": 3,
    "moisture": 3,
    "horticulture": 3,
}

MEDIUM_PRIORITY_TERMS = {
    "seed": 2,
    "compost": 2,
    "pot": 1,
    "leaf": 2,
    "leaves": 2,
    "grow": 2,
    "growing": 2,
    "herb": 2,
    "flower": 1,
    "crop": 2,
    "organic": 1,
}


def calculate_relevance(subject: str, snippet: str) -> int:
    """
    Deterministically calculate whether an email is
    related to plant care.

    Gemini does NOT decide which random email to read.
    """

    text = f"{subject} {snippet}".lower()

    score = 0

    for term, points in HIGH_PRIORITY_TERMS.items():

        if re.search(
            rf"\b{re.escape(term)}\b",
            text
        ):
            score += points

    for term, points in MEDIUM_PRIORITY_TERMS.items():

        if re.search(
            rf"\b{re.escape(term)}\b",
            text
        ):
            score += points

    return score


# ============================================================
# FIND RELEVANT EMAILS
# ============================================================

def get_relevant_emails(service):
    """
    Retrieve recent emails and deterministically filter them
    for plant-care relevance.
    """

    query = f"newer_than:{LOOKBACK_DAYS}d"

    print(
        f"📨 Checking Gmail: last {LOOKBACK_DAYS} days..."
    )

    response = (
        service.users()
        .messages()
        .list(
            userId="me",
            q=query,
            maxResults=MAX_EMAILS
        )
        .execute()
    )

    message_refs = response.get("messages", [])

    if not message_refs:
        return []

    candidates = []

    for ref in message_refs:

        try:
            message = (
                service.users()
                .messages()
                .get(
                    userId="me",
                    id=ref["id"],
                    format="metadata",
                    metadataHeaders=[
                        "Subject",
                        "From",
                        "Date"
                    ]
                )
                .execute()
            )

            payload = message.get("payload", {})
            headers = payload.get("headers", [])

            subject = get_header(headers, "Subject")
            sender = get_header(headers, "From")
            date = get_header(headers, "Date")
            snippet = message.get("snippet", "")

            score = calculate_relevance(
                subject,
                snippet
            )

            if score >= 2:

                candidates.append({
                    "id": ref["id"],
                    "subject": subject,
                    "from": sender,
                    "date": date,
                    "snippet": snippet,
                    "score": score
                })

        except HttpError as error:

            print(
                f"⚠️ Could not inspect Gmail message: {error}"
            )

    candidates.sort(
        key=lambda email: email["score"],
        reverse=True
    )

    return candidates[:5]


# ============================================================
# LOAD FULL CONTENT FOR RELEVANT EMAILS
# ============================================================

def load_email_contents(service, candidates):
    """
    Fetch full message content only after the deterministic
    relevance filter has selected the emails.
    """

    results = []

    for candidate in candidates:

        try:

            message = (
                service.users()
                .messages()
                .get(
                    userId="me",
                    id=candidate["id"],
                    format="full"
                )
                .execute()
            )

            body = extract_message_text(
                message.get("payload", {})
            )

            if not body:
                body = candidate["snippet"]

            body = body[:5000]

            results.append({
                "subject": candidate["subject"],
                "from": candidate["from"],
                "date": candidate["date"],
                "relevance_score": candidate["score"],
                "content": body
            })

        except HttpError as error:

            print(
                f"⚠️ Could not read email: {error}"
            )

    return results


# ============================================================
# GEMINI EMAIL SUMMARIZER
# ============================================================

def summarize_emails(emails):
    """
    Ask Gemini to summarize only the emails that already
    passed the deterministic plant-care filter.
    """

    if not emails:

        return "No relevant plant-care emails found."

    if not GEMINI_API_KEY:

        return "Gmail found relevant emails, but Gemini API key is unavailable."

    email_text = ""

    for index, email in enumerate(emails, start=1):

        email_text += f"""
EMAIL {index}
Subject: {email["subject"]}
From: {email["from"]}
Date: {email["date"]}
Relevance score: {email["relevance_score"]}

Content:
{email["content"]}

--------------------------------
"""

    prompt = f"""
You are the GreenPulse Inbox Agent.

Your job is to summarize emails relevant to caring for a
home plant.

These emails have ALREADY been selected by a deterministic
plant-care relevance filter.

Do not invent information.

Do not include unrelated emails.

Extract only useful plant-care information such as:

- watering advice
- soil moisture advice
- fertilizer/fertiliser advice
- tomato or other plant-care advice
- gardening instructions
- weather-related gardening advice
- warnings or recommendations

If the emails contain conflicting advice, mention the
conflict briefly rather than choosing a side.

Keep the final summary concise, around 2-4 sentences.

EMAILS:
{email_text}
"""

    try:

        model = ChatGoogleGenerativeAI(
            model=GEMINI_MODEL,
            google_api_key=GEMINI_API_KEY,
            temperature=0.2
        )

        structured_model = model.with_structured_output(
            InboxAIOutput,
            method="json_schema"
        )

        result = structured_model.invoke(prompt)

        return result.summary.strip()

    except Exception as error:

        print(
            f"⚠️ Gemini Gmail summarization failed: {error}"
        )

        return (
            "Relevant plant-care emails were found, "
            "but their AI summary is temporarily unavailable."
        )


# ============================================================
# MAIN AGENT
# ============================================================

def get_inbox_summary(force_refresh: bool = False) -> str:
    """
    Main function used by the GreenPulse Care Agent.

    Results are cached for several minutes so the backend
    does NOT call Gmail + Gemini every 30 seconds.
    """

    global _cached_summary
    global _cached_at

    now = time.time()

    if (
        not force_refresh
        and _cached_summary is not None
        and (now - _cached_at) < CACHE_SECONDS
    ):

        return _cached_summary

    print("\n📧 GREENPULSE INBOX AGENT")

    try:

        service = get_gmail_service()

        relevant = get_relevant_emails(
            service
        )

        print(
            f"🔎 Relevant emails found: {len(relevant)}"
        )

        emails = load_email_contents(
            service,
            relevant
        )

        summary = summarize_emails(
            emails
        )

        _cached_summary = summary
        _cached_at = now

        print(
            f"📝 Inbox summary: {summary}"
        )

        return summary

    except Exception as error:

        print(
            f"⚠️ Gmail agent error: {error}"
        )

        fallback = (
            "Gmail summary unavailable."
        )

        _cached_summary = fallback
        _cached_at = now

        return fallback


# ============================================================
# DIRECT TEST
# ============================================================

if __name__ == "__main__":

    print("\n🌱 GREENPULSE GMAIL AGENT")
    print("=" * 50)

    summary = get_inbox_summary(
        force_refresh=True
    )

    print("\nFINAL INBOX SUMMARY:")
    print(summary)

    print("\n✅ Gmail agent test complete.")