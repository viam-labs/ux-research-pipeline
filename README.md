# 🔬 UX Research → Jira Pipeline

Turns UX research session recordings into reviewed, approved Jira tickets — automatically.

## Why This Exists

UX research sessions generate hours of transcript and pages of observer notes. Turning those into actionable Jira tickets is slow, inconsistent, and often delayed weeks. Bugs lose context. Feature requests get lost. Observer insights die in Google Docs.

This pipeline closes the loop: session recording → structured extraction → human review → Jira tickets, in minutes instead of days.

## Goals

1. **Eliminate the transcription-to-ticket bottleneck.** A 1-hour session should produce reviewed, filed tickets the same day — not two weeks later.

2. **Preserve evidence quality.** Every ticket includes timestamps, observer notes, and severity rationale. Engineers get context without re-watching the session.

3. **Human-in-the-loop, not human-out-of-the-loop.** The LLM extracts and structures. A human reviews, adjusts severity, and approves before anything hits Jira. No tickets filed without human sign-off.

4. **Build institutional knowledge over time.** Known issues, decided-against solutions, and cross-session patterns feed back into extraction quality. The system gets smarter as your team uses it.

## Roadmap

| Phase | What | Status |
|-------|------|--------|
| ✅ 1 | Single-prompt extraction (validated 12/12 bugs, 0 hallucinations) | Done |
| ✅ 2 | Streamlit approval UI + Jira integration | Done |
| 🔲 3 | Known issues from live Jira (auto-pull open tickets to avoid duplicates) | Next |
| 🔲 4 | Transcript cleanup with domain glossary (for Whisper-generated transcripts) | Planned |
| 🔲 5 | Cross-session pattern memory (3+ sessions = systemic flag) | Planned |
| 🔲 6 | Module identification (which components were involved per session) | Planned |
| 🔲 7 | Module health correlation (join UX failures with system-level health data) | Planned |

## How It Works

```
Upload transcript + notes
        ↓
  Claude extracts bugs, FRs, summary (structured JSON)
        ↓
  Streamlit UI: review each ticket
  ├── Approve / reject per ticket
  ├── Edit severity and title
  ├── See evidence, steps to reproduce
  └── Borderline tickets flagged with notes
        ↓
  One click → approved tickets created in Jira
```

## Quick Start (Local)

```bash
git clone https://github.com/YOUR_USERNAME/ux-research-pipeline.git
cd ux-research-pipeline
pip install -r requirements.txt
cp .env.example .env
# Fill in .env with your API keys (see below)
streamlit run app.py
```

## Deploy on Lightning AI Studio

1. **Create a Studio** at [lightning.ai](https://lightning.ai)
2. Clone this repo into the Studio terminal:
   ```bash
   git clone https://github.com/YOUR_USERNAME/ux-research-pipeline.git
   cd ux-research-pipeline
   pip install -r requirements.txt
   ```
3. Set environment variables in the Studio:
   ```bash
   export ANTHROPIC_API_KEY=sk-ant-...
   export JIRA_BASE_URL=https://your-org.atlassian.net
   export JIRA_EMAIL=your-email@company.com
   export JIRA_API_TOKEN=your-jira-api-token
   export JIRA_PROJECT_KEY=YOUR_PROJECT
   ```
4. Run the app:
   ```bash
   streamlit run app.py --server.port 8501
   ```
5. Lightning exposes the port — share the URL with your team.

## API Keys

### Claude (Anthropic)
- Go to https://console.anthropic.com/
- Create an API key
- Set as `ANTHROPIC_API_KEY`

### Jira
- Go to https://id.atlassian.com/manage-profile/security/api-tokens
- Create API token (name it "ux-research-pipeline")
- Copy it — you only see it once
- Set as `JIRA_API_TOKEN`
- Also set `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_PROJECT_KEY`

## Usage

### Streamlit App (recommended)

```bash
streamlit run app.py
```

Three-step flow:
1. **Upload** — drag in transcript + notes, fill in session metadata
2. **Review** — see all extracted tickets, approve/reject/edit each one
3. **Submit** — approved tickets created in Jira, links shown

### CLI (for scripted/batch use)

```bash
python src/run.py \
  --transcript sessions/transcript.vtt \
  --notes sessions/notes.md \
  --participant "Jane Doe" \
  --os "Windows 11" \
  --task "Set up platform, connect camera, test detection pipeline" \
  --facilitator "Facilitator Name" \
  --date 2026-02-18 \
  --dry-run
```

Remove `--dry-run` to push directly to Jira (no approval step).

## Project Structure

```
ux-research-pipeline/
├── app.py                    # Streamlit app (main entry point)
├── src/
│   ├── extractor.py          # Claude API — transcript+notes → structured JSON
│   ├── jira_client.py        # Jira API — approved tickets → Jira issues
│   └── run.py                # CLI alternative
├── prompts/
│   ├── extract_bugs.md       # Prompt template (edit to customize extraction)
│   └── known_issues.md       # Issues already in-flight (LLM skips these)
├── sessions/                 # Drop session files here
├── output/                   # CLI saves JSON here
├── .env.example
├── requirements.txt
└── README.md
```

## What Gets Extracted

**Per session:**
- Session summary (3 takeaways, what worked, what didn't)
- Bug tickets with severity, steps to reproduce, expected/actual behavior, evidence
- Feature requests with user's words vs underlying need
- Confidence scores per ticket
- Borderline flags (self-corrected issues, symptoms vs root cause)

**Ticket quality rules baked into the prompt:**
- User self-corrected → not a bug (recovery path worked)
- Multiple symptoms of one issue → file the root cause, cite symptoms as evidence
- Frame at the right altitude ("no component status visibility" not "button X doesn't auto-open")
- Known issues → skip, don't duplicate

**Jira ticket format:**
- Bugs filed as Bug type with severity label and priority mapping
- FRs filed as Story type with feature-request label
- All tickets tagged with `ux-research` and `session-{date}` labels

## Customizing

**Edit the prompt** (`prompts/extract_bugs.md`) to change extraction behavior, severity rules, or output format.

**Add known issues** (`prompts/known_issues.md`) to prevent duplicate tickets for things already being worked on.

**Swap the LLM** — change the model in `src/extractor.py`. Works with any Anthropic model (Opus for best quality, Sonnet for speed/cost).
