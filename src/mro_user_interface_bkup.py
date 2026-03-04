# app.py
import os
import sys
import subprocess
import gradio as gr

API_KEY = os.environ.get("MRO_API_KEY", "wi8onM0ibKgB1clS")

def _safe_decode(b: bytes) -> str:
    """Try utf-8, then cp1252, then latin-1; finally replace undecodable bytes."""
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            continue
    return b.decode("utf-8", errors="replace")

def analyze_mro_video(video_file):
    """
    Generator that streams mro.py stdout/stderr to the Gradio Markdown output.
    Yields the full Markdown report string repeatedly as new output arrives.
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
        header = "### External mro.py run (failed to start)\n\n"
        body = f"Failed to start process: {e}"
        yield header + "```\n" + body + "\n```"
        return

    buffer = ""
    rc = None
    try:
        # Read in binary chunks to avoid platform codec issues
        while True:
            chunk = proc.stdout.read(4096)  # bytes
            if not chunk:
                break
            text = _safe_decode(chunk)
            buffer += text
            # Escape triple backticks to avoid breaking Markdown fences
            safe_output = buffer.replace("```", "``\u200b`")
            header = "### External mro.py run (running)\n\n"
            yield header + "```\n" + safe_output + "\n```"
        rc = proc.wait()
    except Exception as e:
        try:
            proc.kill()
        except Exception:
            pass
        header = "### External mro.py run (reader error)\n\n"
        body = f"Reader error: {e}\n\nPartial output:\n{buffer}"
        yield header + "```\n" + body + "\n```"
        return

    # Final report
    header = f"### External mro.py run (exit code: {rc})\n\n"
    safe_output = buffer.replace("```", "``\u200b`")
    yield header + "```\n" + safe_output + "\n```"

custom_css = """
footer {visibility: hidden}
#header-title {background-color: #000000; color: #76b900; padding: 10px; font-weight: bold; border-bottom: 2px solid #76b900;}
.gradio-container {background-color: #f4f4f4;}
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
                    output_report = gr.Markdown("*Analysis results will appear here after processing...*")
                with gr.TabItem("CHAT"):
                    chatbot = gr.Chatbot(label="MRO Co-Pilot Chat")
                    msg = gr.Textbox(placeholder="Ask a question about this alert...", label="")
                    with gr.Row():
                        ask_btn = gr.Button("Ask")
                        reset_btn = gr.Button("Reset Chat")

    # Gradio supports generator functions for streaming; connect the button to the generator
    analyze_btn.click(fn=analyze_mro_video, inputs=input_video, outputs=output_report)

if __name__ == "__main__":
    demo.launch()