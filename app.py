"""
UX Research → Jira Pipeline
Streamlit app with approval workflow.

Run locally:  streamlit run app.py
Deploy on Lightning Studio: lightning run app app.py
"""

import os
import json
import streamlit as st
from datetime import date
from pathlib import Path

# Add src to path
import sys
sys.path.insert(0, str(Path(__file__).parent / "src"))

from extractor import extract
from jira_client import JiraClient

# ─── Page config ───
st.set_page_config(
    page_title="UX Research → Jira",
    page_icon="🔬",
    layout="wide",
)

# ─── State init ───
if "extracted" not in st.session_state:
    st.session_state.extracted = None
if "approvals" not in st.session_state:
    st.session_state.approvals = {}
if "jira_results" not in st.session_state:
    st.session_state.jira_results = []
if "step" not in st.session_state:
    st.session_state.step = "upload"  # upload → review → submitted


def reset():
    st.session_state.extracted = None
    st.session_state.approvals = {}
    st.session_state.jira_results = []
    st.session_state.step = "upload"


# ─── Header ───
st.title("🔬 UX Research → Jira")
st.caption("Upload a session transcript + observer notes → extract tickets → review & approve → push to Jira")

# Show current step
steps_display = {"upload": "1", "review": "2", "submitted": "3"}
col1, col2, col3 = st.columns(3)
for col, (step_key, label) in zip(
    [col1, col2, col3],
    [("upload", "① Upload & Extract"), ("review", "② Review & Approve"), ("submitted", "③ Submitted")],
):
    if st.session_state.step == step_key:
        col.markdown(f"**→ {label}**")
    else:
        col.markdown(f"<span style='color:#aaa'>{label}</span>", unsafe_allow_html=True)

st.divider()

# ═══════════════════════════════════════════════════════════
# STEP 1: UPLOAD & EXTRACT
# ═══════════════════════════════════════════════════════════
if st.session_state.step == "upload":

    col_left, col_right = st.columns([2, 1])

    with col_left:
        st.subheader("Session Files")
        transcript_file = st.file_uploader(
            "Transcript (.vtt, .txt, .srt)", type=["vtt", "txt", "srt"]
        )
        notes_file = st.file_uploader(
            "Observer Notes (.md, .txt)", type=["md", "txt"]
        )

    with col_right:
        st.subheader("Session Metadata")
        participant = st.text_input("Participant name", placeholder="Eliot Horowitz")
        participant_os = st.text_input("OS", placeholder="Windows 11")
        task = st.text_input(
            "Task",
            placeholder="Set up Viam, connect webcam, build ML detection pipeline",
        )
        facilitator = st.text_input("Facilitator", value="Ana")
        session_date = st.date_input("Session date", value=date.today())

    st.divider()

    # Validate
    ready = all([transcript_file, notes_file, participant, participant_os, task])

    if st.button("🚀 Extract Tickets", type="primary", disabled=not ready, use_container_width=True):
        transcript_text = transcript_file.read().decode("utf-8")
        notes_text = notes_file.read().decode("utf-8")

        session_meta = {
            "participant": participant,
            "os": participant_os,
            "task": task,
            "facilitator": facilitator,
            "date": session_date.isoformat(),
        }

        with st.spinner("Calling Claude to extract bugs and feature requests... (30-60s)"):
            data = extract(transcript_text, notes_text, session_meta)

        if "_error" in data:
            st.error(f"Claude returned invalid JSON: {data['_error']}")
            with st.expander("Raw response"):
                st.code(data.get("_raw", ""))
        else:
            st.session_state.extracted = data
            # Default all to approved
            for bug in data.get("bugs", []):
                st.session_state.approvals[bug["id"]] = "approved"
            for fr in data.get("feature_requests", []):
                st.session_state.approvals[fr["id"]] = "approved"
            st.session_state.step = "review"
            st.rerun()


# ═══════════════════════════════════════════════════════════
# STEP 2: REVIEW & APPROVE
# ═══════════════════════════════════════════════════════════
elif st.session_state.step == "review":
    data = st.session_state.extracted
    session = data.get("session", {})
    summary = data.get("summary", {})
    bugs = data.get("bugs", [])
    frs = data.get("feature_requests", [])

    # ── Summary sidebar ──
    with st.sidebar:
        st.subheader(f"📋 {session.get('participant', '?')}")
        st.caption(f"{session.get('os', '')} · {session.get('date', '')}")

        st.markdown("**Key Takeaways**")
        for t in summary.get("takeaways", []):
            st.markdown(f"- {t}")

        if summary.get("facilitator_interventions"):
            st.markdown("**Facilitator Interventions**")
            for f in summary["facilitator_interventions"]:
                st.markdown(f"- {f}")

        st.divider()
        approved = sum(1 for v in st.session_state.approvals.values() if v == "approved")
        rejected = sum(1 for v in st.session_state.approvals.values() if v == "rejected")
        total = len(st.session_state.approvals)
        st.metric("Approved", f"{approved}/{total}")
        st.metric("Rejected", f"{rejected}/{total}")

        st.divider()
        if st.button("← Back to Upload", use_container_width=True):
            reset()
            st.rerun()

    # ── Bulk actions ──
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        if st.button("✅ Approve All", use_container_width=True):
            for k in st.session_state.approvals:
                st.session_state.approvals[k] = "approved"
            st.rerun()
    with col_b:
        if st.button("❌ Reject All", use_container_width=True):
            for k in st.session_state.approvals:
                st.session_state.approvals[k] = "rejected"
            st.rerun()
    with col_c:
        pass  # spacer

    # ── Bugs ──
    st.subheader(f"🐛 Bugs ({len(bugs)})")

    for i, bug in enumerate(bugs):
        severity_colors = {
            "critical": "🔴",
            "high": "🟠",
            "medium": "🟡",
            "low": "🟢",
        }
        icon = severity_colors.get(bug["severity"], "⚪")
        status = st.session_state.approvals.get(bug["id"], "approved")
        strike = "~~" if status == "rejected" else ""

        with st.expander(
            f"{icon} {bug['id']} — {strike}{bug['title']}{strike}  "
            f"[{bug['severity'].upper()}] "
            f"{'✅' if status == 'approved' else '❌'}",
            expanded=(i < 3),  # auto-expand first 3
        ):
            # Approve / Reject toggle
            col_status, col_sev, col_conf = st.columns([2, 1, 1])
            with col_status:
                new_status = st.radio(
                    "Status",
                    ["approved", "rejected"],
                    index=0 if status == "approved" else 1,
                    key=f"status_{bug['id']}",
                    horizontal=True,
                )
                st.session_state.approvals[bug["id"]] = new_status

            with col_sev:
                sev_options = ["critical", "high", "medium", "low"]
                new_sev = st.selectbox(
                    "Severity",
                    sev_options,
                    index=sev_options.index(bug["severity"]),
                    key=f"sev_{bug['id']}",
                )
                bugs[i]["severity"] = new_sev

            with col_conf:
                st.markdown(f"**Confidence:** {bug.get('confidence', '?')}")
                st.markdown(f"**Type:** {bug.get('type', 'bug')}")

            # Editable title
            new_title = st.text_input(
                "Title", value=bug["title"], key=f"title_{bug['id']}"
            )
            bugs[i]["title"] = new_title

            # Details (read-only display)
            st.markdown("**Steps to Reproduce:**")
            for step in bug.get("steps_to_reproduce", []):
                facilitated = "🔸 " if "[FACILITATED]" in step else ""
                st.markdown(f"- {facilitated}{step}")

            col_exp, col_act = st.columns(2)
            with col_exp:
                st.markdown(f"**Expected:** {bug['expected_behavior']}")
            with col_act:
                st.markdown(f"**Actual:** {bug['actual_behavior']}")

            if bug.get("workaround"):
                st.markdown(f"**Workaround:** {bug['workaround']}")

            st.markdown(f"**Evidence:** {bug['evidence']}")

            if bug.get("note"):
                st.info(f"⚠️ **Note:** {bug['note']}")

    # ── Feature Requests ──
    if frs:
        st.subheader(f"💡 Feature Requests ({len(frs)})")

        for i, fr in enumerate(frs):
            status = st.session_state.approvals.get(fr["id"], "approved")
            strike = "~~" if status == "rejected" else ""

            with st.expander(
                f"💡 {fr['id']} — {strike}{fr['title']}{strike}  "
                f"{'✅' if status == 'approved' else '❌'}"
            ):
                col_status, col_flag = st.columns([2, 1])
                with col_status:
                    new_status = st.radio(
                        "Status",
                        ["approved", "rejected"],
                        index=0 if status == "approved" else 1,
                        key=f"status_{fr['id']}",
                        horizontal=True,
                    )
                    st.session_state.approvals[fr["id"]] = new_status
                with col_flag:
                    if fr.get("is_actually_a_bug"):
                        st.warning("⚠️ May actually be a bug")

                new_title = st.text_input(
                    "Title", value=fr["title"], key=f"title_{fr['id']}"
                )
                frs[i]["title"] = new_title

                st.markdown(f"**User said:** {fr['user_said']}")
                st.markdown(f"**Underlying need:** {fr['underlying_need']}")
                st.markdown(f"**Evidence:** {fr['evidence']}")

    # ── Submit ──
    st.divider()

    approved_bugs = [b for b in bugs if st.session_state.approvals.get(b["id"]) == "approved"]
    approved_frs = [f for f in frs if st.session_state.approvals.get(f["id"]) == "approved"]
    total_approved = len(approved_bugs) + len(approved_frs)

    col_submit, col_download = st.columns(2)

    with col_submit:
        # Check Jira config
        jira_configured = all(
            os.environ.get(k)
            for k in ["JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN", "JIRA_PROJECT_KEY"]
        )

        if not jira_configured:
            st.warning("⚠️ Jira not configured. Set JIRA_* env vars to enable submission.")

        if st.button(
            f"📤 Submit {total_approved} Approved Tickets to Jira",
            type="primary",
            disabled=(total_approved == 0 or not jira_configured),
            use_container_width=True,
        ):
            jira = JiraClient()
            results = []
            progress = st.progress(0)

            for i, bug in enumerate(approved_bugs):
                try:
                    result = jira.create_bug(bug, session)
                    results.append({"type": "bug", "id": bug["id"], **result})
                except Exception as e:
                    results.append({"type": "bug", "id": bug["id"], "error": str(e)})
                progress.progress((i + 1) / total_approved)

            for i, fr in enumerate(approved_frs):
                try:
                    result = jira.create_fr(fr, session)
                    results.append({"type": "fr", "id": fr["id"], **result})
                except Exception as e:
                    results.append({"type": "fr", "id": fr["id"], "error": str(e)})
                progress.progress((len(approved_bugs) + i + 1) / total_approved)

            st.session_state.jira_results = results
            st.session_state.step = "submitted"
            st.rerun()

    with col_download:
        # Always allow JSON download
        download_data = {
            "session": session,
            "summary": summary,
            "approved_bugs": approved_bugs,
            "approved_frs": approved_frs,
            "rejected": [
                k for k, v in st.session_state.approvals.items() if v == "rejected"
            ],
        }
        st.download_button(
            f"💾 Download JSON ({total_approved} approved)",
            data=json.dumps(download_data, indent=2),
            file_name=f"tickets_{session.get('date', 'unknown')}_{session.get('participant', 'unknown').split()[0].lower()}.json",
            mime="application/json",
            use_container_width=True,
        )


# ═══════════════════════════════════════════════════════════
# STEP 3: SUBMITTED
# ═══════════════════════════════════════════════════════════
elif st.session_state.step == "submitted":
    results = st.session_state.jira_results
    successes = [r for r in results if "url" in r]
    failures = [r for r in results if "error" in r]

    if successes:
        st.success(f"✅ Created {len(successes)} Jira tickets!")
        for r in successes:
            st.markdown(f"- **[{r['key']}]({r['url']})** — {r['id']}")

    if failures:
        st.error(f"❌ {len(failures)} tickets failed:")
        for r in failures:
            st.markdown(f"- {r['id']}: {r['error']}")

    st.divider()

    if st.button("🔄 Process Another Session", type="primary", use_container_width=True):
        reset()
        st.rerun()
