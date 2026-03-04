# app.py
import os
import sys
import subprocess
import re
import string
import json
import gradio as gr

API_KEY = os.environ.get("MRO_API_KEY", "wi8onM0ibKgB1clS")

# -------------------------
# Helper: safe decode bytes
# -------------------------
def _safe_decode(b: bytes) -> str:
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            continue
    return b.decode("utf-8", errors="replace")

# -------------------------
# Validation utilities (robust/coercing)
# -------------------------
_STOPWORDS = {
    "the","and","or","to","of","a","an","in","on","for","with","by","is","are",
    "this","that","it","as","be","will","ensure","during","before","after","then",
    "into","from","at","using","used","use"
}

def _coerce_to_text(obj):
    """
    Convert common input shapes to a single string:
      - str -> returned unchanged
      - bytes -> decoded (utf-8 replace)
      - dict -> try common keys ('text','content','output','caption','think'); else JSON dump
      - list -> join elements (coerce each element recursively)
      - other -> str(obj)
    """
    if isinstance(obj, str):
        return obj
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    if isinstance(obj, dict):
        # prefer likely text fields
        for key in ("text", "content", "output", "caption", "think", "result"):
            if key in obj and isinstance(obj[key], (str, bytes)):
                return _coerce_to_text(obj[key])
        # if dict contains a list of events, try to extract captions
        if "events" in obj and isinstance(obj["events"], list):
            captions = []
            for e in obj["events"]:
                if isinstance(e, dict) and "caption" in e:
                    captions.append(_coerce_to_text(e["caption"]))
                else:
                    captions.append(_coerce_to_text(e))
            return "\n".join(captions)
        # fallback to JSON string
        try:
            return json.dumps(obj, ensure_ascii=False)
        except Exception:
            return str(obj)
    if isinstance(obj, list):
        parts = []
        for e in obj:
            parts.append(_coerce_to_text(e))
        return "\n".join(parts)
    # fallback
    try:
        return str(obj)
    except Exception:
        return ""

def _extract_think_block(text):
    """
    Return inner text of the first <think>...</think> block, or the full text if not found.
    Accepts any input type and coerces to string first.
    """
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
    """
    Returns (think_text, missing_list, report_string)
    - think_text: extracted text used for validation
    - missing_list: list of dicts {key,title,definition,keywords_checked}
    - report_string: formatted compliance report (string)
    """
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
            missing.append({
                "key": key,
                "title": title,
                "definition": definition,
                "keywords_checked": keywords
            })

    # build report string
    if missing:
        lines = ["--------------------------------------------------"]
        for m in missing:
            lines.append(f"⚠️ MISSING STEP: **{m['title']}**")
            lines.append(f"   → Expected concepts NOT found in model output.")
            lines.append(f"   → Definition: {m['definition']}")
            lines.append(f"   → This step is compliance‑critical and MUST appear in the timeline.")
            lines.append("")  # blank line
        report = "\n".join(lines).rstrip()
    else:
        report = "All expected steps present. Everything Good."

    return think_text, missing, report

# -------------------------
# Example expected steps (replace with your canonical set)
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
# Main generator: run mro.py, stream results, then validate
# -------------------------
def analyze_mro_video(video_file):
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
        validation_html = (
            "<div class='validation success'>"
            "<strong>Validation</strong><br><div>Process failed to start; no validation performed.</div>"
            "</div>"
        )
        yield md, validation_html
        return

    buffer = ""
    # stream while running
    try:
        while True:
            chunk = proc.stdout.read(4096)
            if not chunk:
                break
            # chunk is bytes; decode safely
            text = _safe_decode(chunk)
            buffer += text
            safe_output = buffer.replace("```", "``\u200b`")
            md = f"### External mro.py run (running)\n\n```\n{safe_output}\n```"
            # while running, show a neutral validation box
            validation_html = (
                "<div class='validation running'><strong>Validation</strong><br>"
                "<div>Running... final validation will appear when the run completes.</div></div>"
            )
            yield md, validation_html
        rc = proc.wait()
    except Exception as e:
        try:
            proc.kill()
        except Exception:
            pass
        md = f"### External mro.py run (reader error)\n\n```\nReader error: {e}\n\nPartial output:\n{buffer}\n```"
        validation_html = (
            "<div class='validation error'><strong>Validation</strong><br>"
            "<div>Reader error occurred; validation not completed.</div></div>"
        )
        yield md, validation_html
        return

    # final markdown
    md = f"### External mro.py run (exit code: {rc})\n\n```\n{buffer.replace('```', '``\u200b`')}\n```"

    # run validation on the accumulated output
    think_text, missing, report = validate_think_against_expected(expected_steps, buffer)
    if missing:
        # build colored HTML report (red for missing)
        items_html = ""
        for m in missing:
            items_html += (
                f"<div class='missing-step'><strong>{m['title']}</strong>"
                f"<div class='def'>{m['definition']}</div></div>"
            )
        validation_html = (
            "<div class='validation error'><h4>⚠️ Validation Report</h4>"
            f"<div class='summary'>Missing steps detected: <strong>{len(missing)}</strong></div>"
            f"{items_html}</div>"
        )
    else:
        validation_html = (
            "<div class='validation success'><h4>✅ Validation Report</h4>"
            "<div class='summary'>All expected steps present. Everything Good.</div></div>"
        )

    # also yield the textual report as part of the Markdown output if you want
    md_with_report = md + "\n\n" + "### Validation (text)\n\n```\n" + report + "\n```"
    yield md_with_report, validation_html

# -------------------------
# UI layout and CSS
# -------------------------
custom_css = """
footer {visibility: hidden}
#header-title {background-color: #000000; color: #76b900; padding: 10px; font-weight: bold; border-bottom: 2px solid #76b900;}
.gradio-container {background-color: #f4f4f4;}
/* Result box styling */
.result-box {
  background: #0b0b0b;
  color: #e6e6e6;
  padding: 12px;
  border-radius: 6px;
  font-family: monospace;
  white-space: pre-wrap;
  max-height: 420px;
  overflow: auto;
  border: 1px solid #333;
}
/* Validation boxes */
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
                    # Results (Markdown) and Validation (HTML) stacked
                    output_report = gr.Markdown("*Analysis results will appear here after processing...*", elem_id="results_md")
                    validation_box = gr.HTML("<div class='validation running'><strong>Validation</strong><br><div>Idle</div></div>", elem_id="validation_html")
                with gr.TabItem("CHAT"):
                    chatbot = gr.Chatbot(label="MRO Co-Pilot Chat")
                    msg = gr.Textbox(placeholder="Ask a question about this alert...", label="")
                    with gr.Row():
                        ask_btn = gr.Button("Ask")
                        reset_btn = gr.Button("Reset Chat")

    analyze_btn.click(fn=analyze_mro_video, inputs=input_video, outputs=[output_report, validation_box])

if __name__ == "__main__":
    demo.launch()