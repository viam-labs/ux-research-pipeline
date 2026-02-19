"""Create Jira tickets from approved UX research data."""

import os
import requests
from requests.auth import HTTPBasicAuth

PRIORITY_MAP = {
    "critical": "Highest",
    "high": "High",
    "medium": "Medium",
    "low": "Low",
}


class JiraClient:
    def __init__(self):
        self.base_url = os.environ["JIRA_BASE_URL"].rstrip("/")
        self.email = os.environ["JIRA_EMAIL"]
        self.token = os.environ["JIRA_API_TOKEN"]
        self.project_key = os.environ["JIRA_PROJECT_KEY"]
        self.label = os.environ.get("JIRA_LABEL", "ux-research")
        self.auth = HTTPBasicAuth(self.email, self.token)
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _api(self, method, path, **kwargs):
        url = f"{self.base_url}/rest/api/3/{path}"
        resp = requests.request(
            method, url, auth=self.auth, headers=self.headers, **kwargs
        )
        resp.raise_for_status()
        return resp.json() if resp.text else {}

    def _make_doc(self, text: str) -> dict:
        """Wrap plain text in Atlassian Document Format."""
        return {
            "version": 1,
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": text}],
                }
            ],
        }

    def create_bug(self, bug: dict, session_meta: dict) -> dict:
        """Create a bug ticket. Returns {key, url}."""
        steps = "\n".join(
            f"{i+1}. {s}" for i, s in enumerate(bug["steps_to_reproduce"])
        )
        desc = (
            f"Steps to Reproduce:\n{steps}\n\n"
            f"Expected: {bug['expected_behavior']}\n\n"
            f"Actual: {bug['actual_behavior']}\n\n"
        )
        if bug.get("workaround"):
            desc += f"Workaround: {bug['workaround']}\n\n"
        desc += (
            f"Evidence: {bug['evidence']}\n\n"
            f"---\n"
            f"Source: UX Session — {session_meta.get('participant', '?')} "
            f"({session_meta.get('os', '?')}), {session_meta.get('date', '?')}\n"
            f"Confidence: {bug.get('confidence', '?')}"
        )

        labels = [
            self.label,
            f"severity-{bug['severity']}",
            f"session-{session_meta.get('date', 'unknown')}",
        ]
        if bug.get("type") == "ux_issue":
            labels.append("ux-issue")

        fields = {
            "project": {"key": self.project_key},
            "summary": f"[{bug['severity'].upper()}] {bug['title']}",
            "issuetype": {"name": "Bug"},
            "priority": {"name": PRIORITY_MAP.get(bug["severity"], "Medium")},
            "labels": labels,
            "description": self._make_doc(desc),
        }

        result = self._api("POST", "issue", json={"fields": fields})
        key = result.get("key", "???")
        return {"key": key, "url": f"{self.base_url}/browse/{key}"}

    def create_fr(self, fr: dict, session_meta: dict) -> dict:
        """Create a feature request ticket. Returns {key, url}."""
        desc = (
            f"What the user said/did:\n{fr['user_said']}\n\n"
            f"Underlying need:\n{fr['underlying_need']}\n\n"
            f"Evidence: {fr['evidence']}\n\n"
        )
        if fr.get("is_actually_a_bug"):
            desc += "⚠️ This may actually be a bug, not a feature request.\n\n"
        desc += (
            f"---\n"
            f"Source: UX Session — {session_meta.get('participant', '?')} "
            f"({session_meta.get('os', '?')}), {session_meta.get('date', '?')}"
        )

        fields = {
            "project": {"key": self.project_key},
            "summary": f"[FR] {fr['title']}",
            "issuetype": {"name": "Story"},
            "labels": [
                self.label,
                "feature-request",
                f"session-{session_meta.get('date', 'unknown')}",
            ],
            "description": self._make_doc(desc),
        }

        result = self._api("POST", "issue", json={"fields": fields})
        key = result.get("key", "???")
        return {"key": key, "url": f"{self.base_url}/browse/{key}"}
