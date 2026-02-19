"""Extract bugs and FRs from a UX research session using Claude."""

import json
import os
from pathlib import Path
from anthropic import Anthropic


PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "extract_bugs.md"
KNOWN_ISSUES_PATH = Path(__file__).parent.parent / "prompts" / "known_issues.md"
EMAIL_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "generate_email.md"


def load_prompt(session_meta: dict) -> str:
    template = PROMPT_PATH.read_text()
    for key, value in session_meta.items():
        template = template.replace(f"{{{key}}}", str(value))

    # Inject known issues if file exists
    if KNOWN_ISSUES_PATH.exists():
        known = KNOWN_ISSUES_PATH.read_text().strip()
        known_block = (
            f"**Known issues (already being worked on — do NOT file new tickets for these):**\n\n"
            f"{known}\n\n"
            f"If you see evidence related to a known issue, mention it in the session summary "
            f"but do not create a separate ticket. If the evidence reveals a NEW dimension of "
            f"a known issue that isn't captured above, you may file it but note the connection."
        )
    else:
        known_block = ""

    template = template.replace("{known_issues}", known_block)
    return template


def extract(transcript: str, notes: str, session_meta: dict) -> dict:
    """Call Claude with transcript + notes, return structured ticket data."""
    client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    system_prompt = load_prompt(session_meta)

    user_message = f"""## Transcript

{transcript}

## Observer Notes

{notes}"""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=8000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )

    raw = response.content[0].text

    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
        if raw.endswith("```"):
            raw = raw.rsplit("```", 1)[0]

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        return {"_raw": raw, "_error": str(e)}


def generate_email(sessions_data: list) -> str:
    """Generate a stakeholder email from one or more session extractions."""
    client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    system_prompt = EMAIL_PROMPT_PATH.read_text()
    user_message = f"""Here are the session results to summarize into an email:

{json.dumps(sessions_data, indent=2)}"""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )
    return response.content[0].text
