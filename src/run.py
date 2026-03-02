#!/usr/bin/env python3
"""
CLI alternative to the Streamlit app.
Use this for scripted/batch processing without the UI.

Usage:
    python src/run.py \
        --transcript sessions/transcript.vtt \
        --notes sessions/notes.md \
        --participant "Eliot Horowitz" \
        --os "Windows 11" \
        --task "Set up Viam, connect webcam, build ML detection pipeline" \
        --facilitator "Ana" \
        --dry-run
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import date

from dotenv import load_dotenv
load_dotenv()

from extractor import extract
from jira_client import JiraClient


def read_file(filepath: str) -> str:
    """Read a text or docx file and return its content as a string."""
    if filepath.endswith('.docx'):
        from docx import Document
        doc = Document(filepath)
        return "\n".join(p.text for p in doc.paragraphs)
    return Path(filepath).read_text()


def main():
    parser = argparse.ArgumentParser(description="UX Research → Jira (CLI)")
    parser.add_argument("--transcript", required=True)
    parser.add_argument("--notes", required=True)
    parser.add_argument("--participant", required=True)
    parser.add_argument("--os", required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--facilitator", default="Unknown")
    parser.add_argument("--date", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    transcript = read_file(args.transcript)
    notes = read_file(args.notes)
    session_date = args.date or date.today().isoformat()

    session_meta = {
        "participant": args.participant,
        "os": args.os,
        "task": args.task,
        "facilitator": args.facilitator,
        "date": session_date,
    }

    session_id = f"{session_date}_{args.participant.split()[0].lower()}"

    print(f"\n{'='*50}")
    print(f"UX Research → Jira (CLI)")
    print(f"{'='*50}")
    print(f"  {args.participant} ({args.os})")
    print(f"  Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    print(f"{'='*50}\n")

    print("[1/3] Extracting...")
    data = extract(transcript, notes, session_meta)

    if "_error" in data:
        print(f"ERROR: {data['_error']}")
        sys.exit(1)

    bugs = data.get("bugs", [])
    frs = data.get("feature_requests", [])
    print(f"  Found {len(bugs)} bugs, {len(frs)} FRs")

    # Save JSON
    out_dir = Path(__file__).parent.parent / "output" / session_id
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "tickets.json").write_text(json.dumps(data, indent=2))
    print(f"\n[2/3] Saved to output/{session_id}/tickets.json")

    if args.dry_run:
        print("\n[3/3] Dry run — tickets NOT pushed to Jira")
        for bug in bugs:
            print(f"  [{bug['severity'].upper()}] {bug['title']}")
        for fr in frs:
            print(f"  [FR] {fr['title']}")
    else:
        print("\n[3/3] Creating Jira tickets...")
        jira = JiraClient()
        for bug in bugs:
            try:
                r = jira.create_bug(bug, data.get("session", {}))
                print(f"  ✅ {r['key']} — {bug['title']}")
            except Exception as e:
                print(f"  ❌ {bug['id']} — {e}")
        for fr in frs:
            try:
                r = jira.create_fr(fr, data.get("session", {}))
                print(f"  ✅ {r['key']} — {fr['title']}")
            except Exception as e:
                print(f"  ❌ {fr['id']} — {e}")

    print(f"\nDone!")


if __name__ == "__main__":
    main()
