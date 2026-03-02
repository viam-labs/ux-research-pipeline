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

from extractor import extract, generate_email
from jira_client import JiraClient


def read_uploaded_file(uploaded_file) -> str:
    if uploaded_file.name.endswith('.docx'):
        from docx import Document
        from io import BytesIO
        doc = Document(BytesIO(uploaded_file.read()))
        return chr(10).join(p.text for p in doc.paragraphs)
    else:
        return uploaded_file.read().decode('utf-8')


# ─── Page config ───
st.set_page_config(
    page_title="UX Research → Jira",
    page_icon="🔬",
    layout="wide",
)

st.markdown("""<style>
    .stTextInput div[data-testid="InputInstructions"] { display: none; }
</style>""", unsafe_allow_html=True)

# ─── State init ───
if "extracted" not in st.session_state:
    st.session_state.extracted = None
if "approvals" not in st.session_state:
    st.session_state.approvals = {}
if "jira_results" not in st.session_state:
    st.session_state.jira_results = []
if "email_draft" not in st.session_state:
    st.session_state.email_draft = None
if "selected_ticket" not in st.session_state:
    st.session_state.selected_ticket = None
if "step" not in st.session_state:
    st.session_state.step = "upload"


def reset():
    st.session_state.extracted = None
    st.session_state.approvals = {}
    st.session_state.jira_results = []
    st.session_state.email_draft = None
    st.session_state.selected_ticket = None
    st.session_state.step = "upload"


SEVERITY_ICONS = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}
STATUS_ICONS = {"approved": "✅", "rejected": "❌", "known": "🔵"}


# ─── Header ───
st.title("🔬 UX Research → Jira")
st.caption("Upload session files → extract tickets → review & approve → push to Jira")

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
        uploaded_files = st.file_uploader(
            "Drop session files (transcript + notes)",
            type=["vtt", "txt", "srt", "docx", "md"],
            accept_multiple_files=True,
        )
        transcript_file = None
        notes_file = None
        for uf in uploaded_files:
            name = uf.name.lower()
            if name.endswith((".vtt", ".srt")):
                transcript_file = uf
            elif name.endswith(".md") or "note" in name or "observer" in name:
                notes_file = uf
            elif name.endswith(".docx"):
                if "transcript" in name:
                    transcript_file = uf
                else:
                    notes_file = uf
            elif name.endswith(".txt"):
                if "note" in name or "observer" in name:
                    notes_file = uf
                elif "transcript" in name:
                    transcript_file = uf
                elif transcript_file is None:
                    transcript_file = uf
                else:
                    notes_file = uf
        if uploaded_files:
            if transcript_file:
                st.caption(f"📄 Transcript: {transcript_file.name}")
            if notes_file:
                st.caption(f"📝 Notes: {notes_file.name}")
            if not transcript_file or not notes_file:
                st.warning("Could not auto-detect. Include 'transcript' or 'notes' in filenames.")

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

    ready = all([transcript_file, notes_file, participant, participant_os, task])

    if st.button("🚀 Extract Tickets", type="primary", disabled=not ready, use_container_width=True):
        transcript_text = read_uploaded_file(transcript_file)
        notes_text = read_uploaded_file(notes_file)

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

    # ── Top bar: participant info + counts ──
    tb1, tb2, tb3, tb4, tb5 = st.columns([4, 1, 1, 1, 1])
    with tb1:
        st.markdown(f"**{session.get('participant', '?')}** · {session.get('os', '')} · {session.get('date', '')}")
    with tb2:
        n_approved = sum(1 for v in st.session_state.approvals.values() if v == "approved")
        st.markdown(f"✅ {n_approved}")
    with tb3:
        n_rejected = sum(1 for v in st.session_state.approvals.values() if v == "rejected")
        st.markdown(f"❌ {n_rejected}")
    with tb4:
        n_known = sum(1 for v in st.session_state.approvals.values() if v == "known")
        st.markdown(f"🔵 {n_known}")
    with tb5:
        if st.button("← Back", use_container_width=True):
            reset()
            st.rerun()

    # ── Collapsed session summary ──
    with st.expander("📋 Session Summary", expanded=False):
        sc1, sc2 = st.columns(2)
        with sc1:
            st.markdown("**Key Takeaways**")
            for t in summary.get("takeaways", []):
                st.markdown(f"- {t}")
            if summary.get("what_worked"):
                st.markdown("**What Worked**")
                for w in summary["what_worked"]:
                    st.markdown(f"- {w}")
        with sc2:
            if summary.get("what_didnt"):
                st.markdown("**What Didn't**")
                for w in summary["what_didnt"]:
                    st.markdown(f"- {w}")
            if summary.get("facilitator_interventions"):
                st.markdown("**Facilitator Interventions**")
                for fi in summary["facilitator_interventions"]:
                    st.markdown(f"- {fi}")

    st.divider()

    # ── Two columns: ticket list (left) + detail panel (right) ──
    col_list, col_detail = st.columns([2, 3])

    # ── LEFT: compact ticket list ──
    with col_list:
        bc1, bc2, bc3 = st.columns(3)
        with bc1:
            if st.button("✅ All", use_container_width=True):
                for k in st.session_state.approvals:
                    st.session_state.approvals[k] = "approved"
                st.rerun()
        with bc2:
            if st.button("❌ All", use_container_width=True):
                for k in st.session_state.approvals:
                    st.session_state.approvals[k] = "rejected"
                st.rerun()
        with bc3:
            if st.button("🔵 All", use_container_width=True):
                for k in st.session_state.approvals:
                    st.session_state.approvals[k] = "known"
                st.rerun()

        # Bugs grouped by severity
        for sev in ["critical", "high", "medium", "low"]:
            sev_bugs = [b for b in bugs if b.get("severity") == sev]
            if not sev_bugs:
                continue
            st.markdown(f"**{SEVERITY_ICONS[sev]} {sev.upper()} ({len(sev_bugs)})**")
            for bug in sev_bugs:
                bid = bug["id"]
                status = st.session_state.approvals.get(bid, "approved")
                icon = STATUS_ICONS.get(status, "⚪")
                flag = " ⚠️" if bug.get("note") else ""
                arrow = "→ " if st.session_state.selected_ticket == bid else ""
                if st.button(f"{icon} {arrow}{bug['title']}{flag}", key=f"sel_{bid}", use_container_width=True):
                    st.session_state.selected_ticket = bid
                    st.rerun()

        # Feature requests
        if frs:
            st.markdown(f"**💡 FEATURE REQUESTS ({len(frs)})**")
            for fr in frs:
                fid = fr["id"]
                status = st.session_state.approvals.get(fid, "approved")
                icon = STATUS_ICONS.get(status, "⚪")
                flag = " ⚠️" if fr.get("is_actually_a_bug") else ""
                arrow = "→ " if st.session_state.selected_ticket == fid else ""
                if st.button(f"{icon} {arrow}{fr['title']}{flag}", key=f"sel_{fid}", use_container_width=True):
                    st.session_state.selected_ticket = fid
                    st.rerun()

    # ── RIGHT: detail panel ──
    with col_detail:
        sel = st.session_state.selected_ticket

        if sel is None:
            st.markdown("### Select a ticket to review")
            st.caption("Click any ticket on the left to see its details and approve, reject, or mark as known.")
        else:
            # Find the item
            item = None
            item_kind = None
            for b in bugs:
                if b["id"] == sel:
                    item = b
                    item_kind = "bug"
                    break
            if not item:
                for f in frs:
                    if f["id"] == sel:
                        item = f
                        item_kind = "fr"
                        break

            if not item:
                st.warning("Ticket not found")

            elif item_kind == "bug":
                status = st.session_state.approvals.get(sel, "approved")
                sev_icon = SEVERITY_ICONS.get(item["severity"], "⚪")

                # Header
                st.markdown(f"### {sev_icon} {item['title']}")
                st.caption(f"{item['id']} · {item.get('type', 'bug')} · confidence: {item.get('confidence', '?')}")

                # Action buttons
                ac1, ac2, ac3, ac4 = st.columns(4)
                with ac1:
                    if st.button("✅ Approve", key="d_a", type="primary" if status == "approved" else "secondary", use_container_width=True):
                        st.session_state.approvals[sel] = "approved"
                        st.rerun()
                with ac2:
                    if st.button("❌ Reject", key="d_r", type="primary" if status == "rejected" else "secondary", use_container_width=True):
                        st.session_state.approvals[sel] = "rejected"
                        st.rerun()
                with ac3:
                    if st.button("🔵 Known", key="d_k", type="primary" if status == "known" else "secondary", use_container_width=True):
                        st.session_state.approvals[sel] = "known"
                        st.rerun()
                with ac4:
                    sev_options = ["critical", "high", "medium", "low"]
                    new_sev = st.selectbox("Severity", sev_options, index=sev_options.index(item["severity"]), key="d_sev", label_visibility="collapsed")
                    for i, b in enumerate(bugs):
                        if b["id"] == sel:
                            bugs[i]["severity"] = new_sev

                st.divider()

                # Warning note if present
                if item.get("note"):
                    st.warning(f"⚠️ {item['note']}")

                # Steps to reproduce
                st.markdown("**Steps to Reproduce**")
                for step in item.get("steps_to_reproduce", []):
                    facilitated = "🔸 " if "[FACILITATED]" in step else ""
                    st.markdown(f"- {facilitated}{step}")

                # Expected / Actual side by side
                ec1, ec2 = st.columns(2)
                with ec1:
                    st.markdown(f"**Expected**")
                    st.markdown(item["expected_behavior"])
                with ec2:
                    st.markdown(f"**Actual**")
                    st.markdown(item["actual_behavior"])

                if item.get("workaround"):
                    st.markdown(f"**Workaround:** {item['workaround']}")

                st.markdown(f"**Evidence**")
                st.markdown(item["evidence"])

            elif item_kind == "fr":
                status = st.session_state.approvals.get(sel, "approved")

                st.markdown(f"### 💡 {item['title']}")
                st.caption(item["id"])

                ac1, ac2, ac3 = st.columns(3)
                with ac1:
                    if st.button("✅ Approve", key="d_a", type="primary" if status == "approved" else "secondary", use_container_width=True):
                        st.session_state.approvals[sel] = "approved"
                        st.rerun()
                with ac2:
                    if st.button("❌ Reject", key="d_r", type="primary" if status == "rejected" else "secondary", use_container_width=True):
                        st.session_state.approvals[sel] = "rejected"
                        st.rerun()
                with ac3:
                    if st.button("🔵 Known", key="d_k", type="primary" if status == "known" else "secondary", use_container_width=True):
                        st.session_state.approvals[sel] = "known"
                        st.rerun()

                st.divider()

                if item.get("is_actually_a_bug"):
                    st.warning("⚠️ This may actually be a bug, not a feature request")

                st.markdown(f"**User said:** {item['user_said']}")
                st.markdown(f"**Underlying need:** {item['underlying_need']}")
                st.markdown(f"**Evidence:** {item['evidence']}")

    # ═══════════════════════════════════════════════════════════
    # ACTIONS BAR
    # ═══════════════════════════════════════════════════════════
    st.divider()

    approved_bugs = [b for b in bugs if st.session_state.approvals.get(b["id"]) == "approved"]
    approved_frs = [f for f in frs if st.session_state.approvals.get(f["id"]) == "approved"]
    total_approved = len(approved_bugs) + len(approved_frs)

    col_submit, col_download, col_summary, col_email = st.columns(4)

    with col_submit:
        jira_configured = all(
            os.environ.get(k)
            for k in ["JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN", "JIRA_PROJECT_KEY"]
        )
        if not jira_configured:
            st.warning("⚠️ Set JIRA_* env vars")
        if st.button(
            f"📤 Submit {total_approved} to Jira",
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
        download_data = {
            "session": session,
            "summary": summary,
            "approved_bugs": approved_bugs,
            "approved_frs": approved_frs,
            "rejected": [k for k, v in st.session_state.approvals.items() if v == "rejected"],
            "known": [k for k, v in st.session_state.approvals.items() if v == "known"],
        }
        st.download_button(
            f"💾 JSON ({total_approved})",
            data=json.dumps(download_data, indent=2),
            file_name=f"tickets_{session.get('date', 'unknown')}_{session.get('participant', 'unknown').split()[0].lower()}.json",
            mime="application/json",
            use_container_width=True,
        )

    with col_summary:
        summary_md = f"# UX Session Summary\n\n"
        summary_md += f"**Participant:** {session.get('participant', '?')}\n"
        summary_md += f"**OS:** {session.get('os', '?')}\n"
        summary_md += f"**Task:** {session.get('task', '?')}\n"
        summary_md += f"**Date:** {session.get('date', '?')}\n\n"
        summary_md += f"## Key Takeaways\n\n"
        for t in summary.get("takeaways", []):
            summary_md += f"- {t}\n"
        summary_md += f"\n## What Worked\n\n"
        for w in summary.get("what_worked", []):
            summary_md += f"- {w}\n"
        summary_md += f"\n## What Didn't\n\n"
        for w in summary.get("what_didnt", []):
            summary_md += f"- {w}\n"
        if summary.get("facilitator_interventions"):
            summary_md += f"\n## Facilitator Interventions\n\n"
            for fi in summary["facilitator_interventions"]:
                summary_md += f"- {fi}\n"
        summary_md += f"\n## Approved Bugs ({len(approved_bugs)})\n\n"
        for b in approved_bugs:
            summary_md += f"### [{b['severity'].upper()}] {b['title']}\n"
            summary_md += f"- **Steps:** {'; '.join(b.get('steps_to_reproduce', []))}\n"
            summary_md += f"- **Expected:** {b['expected_behavior']}\n"
            summary_md += f"- **Actual:** {b['actual_behavior']}\n"
            summary_md += f"- **Evidence:** {b['evidence']}\n\n"
        if approved_frs:
            summary_md += f"\n## Feature Requests ({len(approved_frs)})\n\n"
            for fr_item in approved_frs:
                summary_md += f"### {fr_item['title']}\n"
                summary_md += f"- **User said:** {fr_item['user_said']}\n"
                summary_md += f"- **Underlying need:** {fr_item['underlying_need']}\n\n"
        known_items = [k for k, v in st.session_state.approvals.items() if v == "known"]
        if known_items:
            summary_md += f"\n## Known Issues (skipped)\n\n"
            for kid in known_items:
                for b in bugs:
                    if b["id"] == kid:
                        summary_md += f"- {b['title']}\n"
                for f in frs:
                    if f["id"] == kid:
                        summary_md += f"- {f['title']}\n"
        st.download_button(
            "📝 Summary",
            data=summary_md,
            file_name=f"summary_{session.get('date', 'unknown')}_{session.get('participant', 'unknown').split()[0].lower()}.md",
            mime="text/markdown",
            use_container_width=True,
        )

    with col_email:
        if st.button("📧 Email", use_container_width=True):
            st.session_state.email_draft = "__SHOW_EMAIL_FORM__"
            st.rerun()

    # ── Email generation ──
    if st.session_state.email_draft is not None:
        st.divider()
        st.subheader("📧 Stakeholder Email")
        if st.session_state.email_draft == "__SHOW_EMAIL_FORM__":
            el1, el2 = st.columns(2)
            with el1:
                notes_link = st.text_input("Notes link", placeholder="https://docs.google.com/...")
            with el2:
                video_link = st.text_input("Video link", placeholder="https://drive.google.com/...")
            if st.button("🚀 Generate Email Draft", type="primary", use_container_width=True):
                email_input = {
                    "session": {**session, "notes_link": notes_link, "video_link": video_link},
                    "summary": summary,
                    "approved_bugs": approved_bugs,
                    "approved_frs": approved_frs,
                }
                with st.spinner("Generating email draft..."):
                    st.session_state.email_draft = generate_email([email_input])
                st.rerun()
        else:
            edited_email = st.text_area("Edit before sending:", value=st.session_state.email_draft, height=400)
            ee1, ee2 = st.columns(2)
            with ee1:
                st.download_button(
                    "📋 Download as .txt",
                    data=edited_email,
                    file_name=f"email_{session.get('date', 'unknown')}.txt",
                    mime="text/plain",
                    use_container_width=True,
                )
            with ee2:
                if st.button("← Back", use_container_width=True):
                    st.session_state.email_draft = None
                    st.rerun()


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
