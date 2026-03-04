# SMART_MRO_VER1
Deliver a Smart MRO system that uses video and AI to ensure error‑free aerospace maintenance by automatically validating procedures, generating compliance records, and preventing latent defects.
Overview
This README explains how to run mro_user_interface.py on the Neboius VM using the VLLM API key and the Neboius VM IPA credential. Running the script will start a local web UI where you can upload a sample video from the specified location and validate results using the generated validation report.

Prerequisites
- Python 3.9+ installed on the VM.
- Required Python packages installed (see Install dependencies).
- Neboius VM IPA credential and VLLM API key available as environment variables.
- Sample video file placed at the path referenced below.Path :testvideo :video2.mp4

Environment variables
Set the following environment variables on the Neboius VM before running the script:
- NEBOIUS_VM_IPA — Neboius VM IPA credential.
- VLLM_API_KEY — VLLM API key used by the UI backend.
Example (Linux/macOS):
export NEBOIUS_VM_IPA="your_neboius_vm_ipa_value"
export VLLM_API_KEY="your_vllm_api_key_value"


Example (Windows PowerShell):
$env:NEBOIUS_VM_IPA="your_neboius_vm_ipa_value"
$env:VLLM_API_KEY="your_vllm_api_key_value"



Install dependencies
Install required packages from requirements.txt or install common dependencies directly:
pip install -r requirements.txt
# or, if no requirements file:
pip install flask fastapi uvicorn requests python-multipart



Run the user interface
- From the project root o run:
python mro_user_interface.py


- The script will start a local server and print the local host URL (for example http://127.0.0.1:8000 or http://localhost:5000).
- Open the printed URL in a browser and click to open the UI.
Upload sample video and validate- Sample video location: place the sample video at the project path ./sample_videos/sample.mp4 (or update the UI configuration to point to your chosen path).
- In the UI, use the Upload control to select the sample video from the specified location.
- After upload, click Process or Validate (UI button label) to run the analysis pipeline.
- The UI will produce a validation report; view it in the UI or download it from the results panel.
Expected outputs- Processed video preview or playback in the UI.
- Validation report in JSON and human-readable formats summarizing checks and metrics.
- Log entries in the console showing processing steps and any warnings or errors.
