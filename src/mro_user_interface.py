# app.py
import os
import sys
import subprocess
import re
import string
import json
import gradio as gr
import re
API_KEY = os.environ.get("MRO_API_KEY", "wi8onM0ibKgB1clS")

# -------------------------
# Helpers (decoding, coercion, validation)
# -------------------------
def _safe_decode(b: bytes) -> str:
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            continue
    return b.decode("utf-8", errors="replace")

_STOPWORDS = {
    "the","and","or","to","of","a","an","in","on","for","with","by","is","are",
    "this","that","it","as","be","will","ensure","during","before","after","then",
    "into","from","at","using","used","use"
}

def _coerce_to_text(obj):
    if isinstance(obj, str):
        return obj
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    if isinstance(obj, dict):
        for key in ("text", "content", "output", "caption", "think", "result"):
            if key in obj and isinstance(obj[key], (str, bytes)):
                return _coerce_to_text(obj[key])
        if "events" in obj and isinstance(obj["events"], list):
            captions = []
            for e in obj["events"]:
                if isinstance(e, dict) and "caption" in e:
                    captions.append(_coerce_to_text(e["caption"]))
                else:
                    captions.append(_coerce_to_text(e))
            return "\n".join(captions)
        try:
            return json.dumps(obj, ensure_ascii=False)
        except Exception:
            return str(obj)
    if isinstance(obj, list):
        parts = []
        for e in obj:
            parts.append(_coerce_to_text(e))
        return "\n".join(parts)
    try:
        return str(obj)
    except Exception:
        return ""

def _extract_think_block(text):
    s = _coerce_to_text(text)
    m = re.search(r"<think>(.*?)</think>", s, re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else s.strip()

def _keywords_from_definition(definition, min_len=4):
    tokens = re.findall(r"\w+", definition.lower())
    keywords = [t for t in tokens if len(t) >= min_len and t not in _STOPWORDS]
    seen = set(); out = []
    for k in keywords:
        if k not in seen:
            seen.add(k); out.append(k)
    return out

def validate_think_against_expected(expected_steps, response_text):
    think_text = _extract_think_block(response_text)
    normalized = think_text.lower()
    normalized = normalized.translate(str.maketrans(string.punctuation, " " * len(string.punctuation)))
    missing = []
    for key, data in expected_steps.items():
        title = data.get("title", key)
        definition = data.get("definition", "")
        keywords = _keywords_from_definition(definition)
        found = any(re.search(r"\b" + re.escape(kw) + r"\b", normalized) for kw in keywords)
        if not found:
            missing.append({"key": key, "title": title, "definition": definition, "keywords_checked": keywords})
    # textual report
    if missing:
        lines = ["--------------------------------------------------"]
        for m in missing:
            lines.append(f"⚠️ MISSING STEP: **{m['title']}**")
            lines.append(f"   → Expected concepts NOT found in model output.")
            lines.append(f"   → Definition: {m['definition']}")
            lines.append(f"   → This step is compliance‑critical and MUST appear in the timeline.")
            lines.append("")
        report = "\n".join(lines).rstrip()
    else:
        report = "All expected steps present. Everything Good."
    return think_text, missing, report

# -------------------------
# expected_steps (same as before)
# -------------------------
expected_steps = {
    "1_Damage_Marking_and_Hole_Preparation": {
        "title": "Damage Marking and Hole Preparation",
        "definition": "Identify dents on the wing surface and enlarge or align holes to prepare the repair zone for structural correction."
    },
    "2_Surface_Cleaning_and_Corrosion_Removal": {
        "title": "Surface Cleaning and Corrosion Removal",
        "definition": "Perform surface cleaning and corrosion removal before installing the new panel or patch, ensuring bare metal and proper surface treatment."
    },
    "3_Additional_Surface_Preparation": {
        "title": "Additional Surface Preparation",
        "definition": "Apply alodine conversion coating, approved primer, and a corrosion-inhibiting compound to the cleaned area; allow specified dwell times and cure cycles to ensure long-term protection."
    },
    "4_Patch_Plate_Installation": {
        "title": "Patch Plate Installation",
        "definition": "Position the metal patch plate accurately over the treated area and secure it to maintain alignment during repair."
    },
    "5_Panel_Shaping_and_Installation": {
        "title": "Panel Shaping and Installation",
        "definition": "Refine the replacement panel for proper fit, then install it with sealant and secure it using approved rivet patterns and torque."
    },
    "6_Final_Finish_and_Quality_Verification": {
        "title": "Final Finish and Quality Verification",
        "definition": "Restore the surface with paint and conduct a final inspection to confirm structural integrity, alignment, and airworthiness."
    },
    "7_NDT_and_Bond_Verification": {
        "title": "Non Destructive Testing and Bond Verification",
        "definition": "Perform non-destructive testing such as dye-penetrant, ultrasonic, or eddy-current inspections to verify crack absence and bond integrity; conduct bond strength tests and torque verification on fasteners."
    }
}

# -------------------------
# Main generator: run mro.py, stream results, then validate and store final data
# -------------------------
def analyze_mro_video(video_file, state):
    """
    state is a dict-like object stored in gr.State that will be updated with:
      state['raw_output'], state['think_text'], state['events'], state['validation_report'], state['missing']
    """
    cmd = [
        sys.executable, "mro.py",
        "--host", "89.169.102.197",
        "--port", "8000",
        "--api-key", API_KEY,
        "--tests", "4s_MRO_json"
    ]

    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except Exception as e:
        md = f"### External mro.py run (failed to start)\n\n```\nFailed to start process: {e}\n```"
        validation_html = "<div class='validation success'><strong>Validation</strong><br><div>Process failed to start; no validation performed.</div></div>"
        # clear state
        state.update({
            "raw_output": "",
            "think_text": "",
            "events": [],
            "validation_report": "Process failed to start; no validation performed.",
            "missing": []
        })
        yield md, validation_html, state
        return

    buffer = ""
    try:
        while True:
            chunk = proc.stdout.read(4096)
            if not chunk:
                break
            text = _safe_decode(chunk)
            buffer += text
            safe_output = buffer.replace("```", "``\u200b`")
            md = f"### External mro.py run (running)\n\n```\n{safe_output}\n```"
            validation_html = "<div class='validation running'><strong>Validation</strong><br><div>Running... final validation will appear when the run completes.</div></div>"
            yield md, validation_html, state
        rc = proc.wait()
    except Exception as e:
        try:
            proc.kill()
        except Exception:
            pass
        md = f"### External mro.py run (reader error)\n\n```\nReader error: {e}\n\nPartial output:\n{buffer}\n```"
        validation_html = "<div class='validation error'><strong>Validation</strong><br><div>Reader error occurred; validation not completed.</div></div>"
        state.update({
            "raw_output": buffer,
            "think_text": _extract_think_block(buffer),
            "events": [],
            "validation_report": "Reader error occurred; validation not completed.",
            "missing": []
        })
        yield md, validation_html, state
        return

    md = f"### External mro.py run (exit code: {rc})\n\n```\n{buffer.replace('```', '``\u200b`')}\n```"

    # try to extract JSON events from buffer (simple heuristic)
    events = []
    try:
        # find the first JSON array in the buffer
        m = re.search(r"(\[\s*\{.*\}\s*\])", buffer, re.DOTALL)
        if m:
            events = json.loads(m.group(1))
    except Exception:
        events = []

    think_text, missing, report = validate_think_against_expected(expected_steps, buffer)

    # update state for chat use
    state.update({
        "raw_output": buffer,
        "think_text": think_text,
        "events": events,
        "validation_report": report,
        "missing": missing
    })

    # build validation_html
    if missing:
        items_html = ""
        for m in missing:
            items_html += f"<div class='missing-step'><strong>{m['title']}</strong><div class='def'>{m['definition']}</div></div>"
        validation_html = f"<div class='validation error'><h4>⚠️ Validation Report</h4><div class='summary'>Missing steps detected: <strong>{len(missing)}</strong></div>{items_html}</div>"
    else:
        validation_html = "<div class='validation success'><h4>✅ Validation Report</h4><div class='summary'>All expected steps present. Everything Good.</div></div>"

    # include textual report in Markdown output
    md_with_report = md + "\n\n" + "### Validation (text)\n\n```\n" + report + "\n```"
    yield md_with_report, validation_html, state

# -------------------------
# Chat handler: answer from stored state
# -------------------------


# -------------------------
# Chat utilities and handler (replace previous chat_answer / ask_wrapper wiring)
# -------------------------
import re

def _append_message(history, role, content):
    """
    history: list of dicts [{'role':..., 'content':...}, ...] or legacy formats.
    Returns a new list with the appended message (dict format).
    """
    history = history or []
    normalized = []
    for m in history:
        if isinstance(m, dict) and "role" in m and "content" in m:
            normalized.append(m)
        elif isinstance(m, (list, tuple)) and len(m) == 2:
            # legacy tuple like ("User","text") -> convert to role/content
            role_guess = "user" if str(m[0]).lower().startswith("user") else "assistant"
            normalized.append({"role": role_guess, "content": str(m[1])})
        else:
            # fallback: treat as assistant content
            normalized.append({"role": "assistant", "content": str(m)})
    normalized.append({"role": role, "content": content})
    return normalized




def _normalize_history(history):
    """
    Ensure history is a list of dicts with 'role' and 'content'.
    Accepts legacy tuple formats like ("User","text") and converts them.
    """
    history = history or []
    normalized = []
    for m in history:
        if isinstance(m, dict) and "role" in m and "content" in m:
            normalized.append(m)
        elif isinstance(m, (list, tuple)) and len(m) == 2:
            role_guess = "user" if str(m[0]).lower().startswith("user") else "assistant"
            normalized.append({"role": role_guess, "content": str(m[1])})
        else:
            normalized.append({"role": "assistant", "content": str(m)})
    return normalized

def _append_message(history, role, content):
    h = _normalize_history(history)
    h.append({"role": role, "content": content})
    return h

def chat_answer(question, state, chat_history):
    """
    Gradio-compatible chat handler.
    Returns: (updated_chat_history_list_of_dicts, state)
    """
    # normalize incoming history and append user message
    history = _append_message(chat_history, "user", question)

    # retrieve stored dashboard data
    raw = state.get("raw_output", "") or ""
    think = state.get("think_text", "") or ""
    events = state.get("events", []) or []
    report = state.get("validation_report", "No validation available.")
    missing = state.get("missing", [])

    q = (question or "").lower().strip()

    # 1) Validation questions
    if any(tok in q for tok in
           ("validation", "missing", "compliance", "compliant", "not compliant", "missing step")):
        answer = report

    # 2) Timestamp / event lookup
    elif any(tok in q for tok in ("when", "timestamp", "time", "start", "end", "what time")):
        keywords = re.findall(r"\w+", q)
        matches = []
        for ev in events:
            cap = ev.get("caption", "").lower()
            if any(k in cap for k in keywords if len(k) > 3):
                matches.append(ev)
        if matches:
            lines = [f"{m.get('start', '?')} - {m.get('end', '?')}: {m.get('caption', '')}" for m in matches]
            answer = "Found matching events:\n" + "\n".join(lines)
        elif events:
            lines = [f"{e.get('start', '?')} - {e.get('end', '?')}: {e.get('caption', '')}" for e in events]
            answer = "No direct match found; full event timeline:\n" + "\n".join(lines)
        else:
            answer = "No event timeline available to answer timing questions."

    # 3) General QA: keyword overlap search
    else:
        corpus = []
        for s in re.split(r'(?<=[.!?])\s+', think):
            if s.strip():
                corpus.append(("think", s.strip()))
        for ev in events:
            cap = ev.get("caption", "")
            if cap:
                corpus.append(("event", cap.strip()))

        q_tokens = [t for t in re.findall(r"\w+", q) if len(t) > 3]
        best = None
        best_score = 0
        for src, text in corpus:
            txt = text.lower()
            score = sum(1 for t in q_tokens if t in txt)
            if score > best_score:
                best_score = score
                best = (src, text)
        if best and best_score > 0:
            answer = f"Based on the dashboard content ({best[0]}): {best[1]}"
        elif think:
            summary = think if len(think) < 800 else think[:800] + "..."
            answer = f"I couldn't find a precise match; here's the dashboard summary:\n{summary}"
        elif raw:
            answer = "No structured summary available; raw output contains details. Ask about 'validation' or 'timeline'."
        else:
            answer = "No dashboard data available yet. Run AI Validation first."

    # append assistant reply and return normalized history
    history = _append_message(history, "assistant", answer)
    return history, state

def _reset_all():
    empty_state = {"raw_output": "", "think_text": "", "events": [], "validation_report": "", "missing": []}
    return [], empty_state

# --- Wiring (replace previous ask_btn/reset_btn wiring) ---
# ask_btn.click(fn=chat_answer, inputs=[msg, state, chatbot], outputs=[chatbot, state])
# reset_btn.click(fn=_reset_all, inputs=None, outputs=[chatbot, state])
def _reset_all():
    empty_state = {"raw_output":"", "think_text":"", "events":[], "validation_report":"", "missing":[]}
    return [], empty_state

# Wiring (replace previous wiring lines)
# ask_btn.click(fn=chat_answer, inputs=[msg, state, chatbot], outputs=[chatbot, state])
# reset_btn.click(fn=_reset_all, inputs=None, outputs=[chatbot, state])
# -------------------------
# UI layout and CSS
# -------------------------
custom_css = """
footer {visibility: hidden}
#header-title {background-color: #000000; color: #76b900; padding: 20px; font-weight: bold; border-bottom: 2px solid #76b900;}
.gradio-container {background-color: #f4f4f4;}
.validation { padding: 12px; border-radius: 6px; margin-top: 8px; }
.validation.running { background: #fff7e6; border: 1px solid #ffd27a; color: #5a3b00; }
.validation.success { background: #e9f7ee; border: 1px solid #8fd19e; color: #0b5a2b; }
.validation.error { background: #fdecea; border: 1px solid #f5a6a6; color: #6a0b0b; }
.missing-step { margin-top: 8px; padding: 8px; background: #fff0f0; border-radius: 4px; }
.missing-step .def { font-size: 0.95em; color: #4b1a1a; margin-top: 4px; }
"""

with gr.Blocks(css=custom_css, title="MRO AI Agent") as demo:
    gr.HTML("<div id='header-title'>| SMART MRO AI AGENT  for Aerospace Maintenance and Repair Inspection </div>")
    with gr.Row():
        with gr.Column(scale=1):
            gr.Markdown("### Preview")
            input_video = gr.Video(label="Input Maintenance Feed")
            analyze_btn = gr.Button("RUN AI VALIDATION", variant="primary")
        with gr.Column(scale=2):
            with gr.Tabs():
                with gr.TabItem("DASHBOARD"):
                    output_report = gr.Markdown("*Analysis results will appear here after processing...*", elem_id="results_md")
                    validation_box = gr.HTML("<div class='validation running'><strong>Validation</strong><br><div>Idle</div></div>", elem_id="validation_html")
                with gr.TabItem("CHAT"):
                    chatbot = gr.Chatbot(label="MRO Co-Pilot Chat")
                    msg = gr.Textbox(placeholder="Ask a question about this alert...", label="")
                    with gr.Row():
                        ask_btn = gr.Button("Ask")
                        reset_btn = gr.Button("Reset Chat")

    # state to hold dashboard outputs for chat
    state = gr.State({
        "raw_output": "",
        "think_text": "",
        "events": [],
        "validation_report": "",
        "missing": []
    })

    # connect analyze button (streaming generator) -> outputs: results_md, validation_html, state
    analyze_btn.click(fn=analyze_mro_video, inputs=[input_video, state], outputs=[output_report, validation_box, state])

    # chat wiring: ask_btn uses state and chat history
    def ask_wrapper(question, state, chat_history):
        answer, new_history = chat_answer(question, state, chat_history or [])
        return new_history, state

    ask_btn.click(fn=ask_wrapper, inputs=[msg, state, chatbot], outputs=[chatbot, state])
    reset_btn.click(lambda: ([], {"raw_output":"", "think_text":"", "events":[], "validation_report":"", "missing":[]}), inputs=None, outputs=[chatbot, state])

if __name__ == "__main__":
    demo.launch()