#!/usr/bin/env python3
# Copyright 2026 NVIDIA CORPORATION & AFFILIATES
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0

"""
Cosmos Reason 2 Prompt Tests

This script demonstrates various Cosmos Reason 2 capabilities through a series of
prompt tests covering vision-language tasks like image/video understanding,
temporal localization, robotics reasoning, and synthetic data critique.

Usage:
    python cosmos_reason2_tests.py --host <IP> --port <PORT> --api-key <KEY>

    # Using environment variables:
    export VLLM_ENDPOINT="IP:PORT"
    export VLLM_API_KEY="your-api-key"
    python cosmos_reason2_tests.py

For more details on prompting patterns, see the Cosmos Reason 2 Prompt Guide:
https://github.com/nvidia-cosmos/cosmos-cookbook/blob/main/docs/core_concepts/prompt_guide/reason_guide.md
"""

import argparse
import json
import os
import sys
from typing import Optional
from mro_Validation import validate_steps,extract_json_array
import re
import string
try:
    from openai import OpenAI
except ImportError:
    print("Error: openai package not found. Install it with: pip install openai")
    sys.exit(1)


# =============================================================================
# Test Definitions
# =============================================================================

TESTS = {

    "4_temporal_json": {
        "name": "Temporal Localization (JSON Output)",
        "description": "Video events with timestamps in JSON format",
        "media_type": "video_url",
        "media_url": "https://assets.ngc.nvidia.com/products/api-catalog/cosmos-reason1-7b/car_curb.mp4",
        "prompt": """Describe the notable events in the provided video. Provide the result in json format with 'mm:ss.ff' format for time depiction for each event. Use keywords 'start', 'end' and 'caption' in the json output.

Answer the question using the following format:

<think>
Your reasoning.
</think>

Write your final answer immediately after the </think> tag and include the timestamps.""",
        "max_tokens": 2048,
        "temperature": 0.6,
        "top_p": 0.95,
        "fps": 4,
    },
    "4s_MRO_json": {
        "name": "MRO validation agent(JSON Output)",
        "description": "Video events with timestamps in JSON format to validate the repair compliance",
        "media_type": "video_url",
        "media_url": "https://drive.google.com/uc?export=download&id=1AapAZpyzXPLoIhnDEvFWcesA4cJ6-lct",
        "prompt": """Describe the notable events in the provided video. Provide the result in json format with 'mm:ss.ff' format for time depiction for each event. Use keywords 'start', 'end' and 'caption' in the json output.

Answer the question using the following format:

<think>
Your reasoning.
</think>

Write your final answer immediately after the </think> tag and include the timestamps.""",
        "max_tokens": 2048,
        "temperature": 0.6,
        "top_p": 0.95,
        "fps": 4,
    },

}


# =============================================================================
# Helper Functions
# =============================================================================


def parse_args():
    """Parse command-line arguments with environment variable fallbacks."""
    parser = argparse.ArgumentParser(
        description="Run Cosmos Reason 2 prompt tests",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Direct arguments:
    python cosmos_reason2_tests.py --host 89.169.115.247 --port 8000 --api-key mykey

    # Using environment variables:
    export VLLM_ENDPOINT="89.169.115.247:8000"
    export VLLM_API_KEY="mykey"
    python cosmos_reason2_tests.py

    # Run specific tests:
    python cosmos_reason2_tests.py --tests 1_basic_image 3_temporal_localization

    # List available tests:
    python cosmos_reason2_tests.py --list
        """,
    )

    # Connection settings
    parser.add_argument(
        "--host",
        type=str,
        default=os.environ.get("VLLM_HOST"),
        help="Host IP address (or set VLLM_HOST env var)",
    )
    parser.add_argument(
        "--port",
        type=str,
        default=os.environ.get("VLLM_PORT", "8000"),
        help="Port number (default: 8000, or set VLLM_PORT env var)",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=os.environ.get("VLLM_API_KEY", "not-used"),
        help="API key (or set VLLM_API_KEY env var)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="nvidia/Cosmos-Reason2-2B",
        help="Model name (default: nvidia/Cosmos-Reason2-2B)",
    )

    # Test selection
    parser.add_argument(
        "--tests",
        nargs="+",
        choices=list(TESTS.keys()) + ["all"],
        default=["all"],
        help="Which tests to run (default: all)",
    )
    parser.add_argument(
        "--list", action="store_true", help="List available tests and exit"
    )

    args = parser.parse_args()

    # Handle VLLM_ENDPOINT environment variable (IP:PORT format)
    vllm_endpoint = os.environ.get("VLLM_ENDPOINT")
    if vllm_endpoint and not args.host:
        if ":" in vllm_endpoint:
            args.host, args.port = vllm_endpoint.rsplit(":", 1)
        else:
            args.host = vllm_endpoint

    return args


def list_tests():
    """Print available tests and their descriptions."""
    print("\n" + "=" * 70)
    print("Available Cosmos Reason 2 Tests")
    print("=" * 70)
    for test_id, test in TESTS.items():
        print(f"\n  {test_id}")
        print(f"    Name: {test['name']}")
        print(f"    Description: {test['description']}")
        print(f"    Media: {test['media_type']}")
    print("\n" + "=" * 70)
    print("Run with: python cosmos_reason2_tests.py --tests <test_id> [<test_id> ...]")
    print("Run all:  python cosmos_reason2_tests.py --tests all")
    print("=" * 70 + "\n")


def create_client(host: str, port: str, api_key: str) -> OpenAI:
    """Create and return an OpenAI client configured for vLLM."""
    base_url = f"http://{host}:{port}/v1"
    print(f"Connecting to: {base_url}")
    return OpenAI(base_url=base_url, api_key=api_key)


def run_test(
    client: OpenAI, model: str, test_id: str, test_config: dict
) -> Optional[str]:
    """Run a single test and return the result."""
    print(f"\n{'=' * 70}")
    print(f"Test: {test_config['name']}")
    print(f"Description: {test_config['description']}")
    print(f"{'=' * 70}")

    # Build message content (media first, then text - per prompt guide)
    content = []

    # Add media (image or video)
    media_type = test_config["media_type"]
    media_url = test_config["media_url"]

    if media_type == "image_url":
        content.append({"type": "image_url", "image_url": {"url": media_url}})
    elif media_type == "video_url":
        content.append({"type": "video_url", "video_url": {"url": media_url}})

    # Add text prompt
    content.append({"type": "text", "text": test_config["prompt"]})

    # Build messages
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": content},
    ]

    # Build extra_body for video FPS if specified
    extra_body = {}
    if "fps" in test_config:
        extra_body["media_io_kwargs"] = {"video": {"fps": test_config["fps"]}}

    print(f"\nMedia URL: {media_url}")
    print(
        f"Prompt: {test_config['prompt'][:100]}..."
        if len(test_config["prompt"]) > 100
        else f"Prompt: {test_config['prompt']}"
    )
    print("\nWaiting for response...")

    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=test_config.get("max_tokens", 1024),
            temperature=test_config.get("temperature", 0.7),
            top_p=test_config.get("top_p", 0.8),
            extra_body=extra_body if extra_body else None,
        )

        result = response.choices[0].message.content

        print(f"\n{'-' * 70}")
        print("Response:")
        print(f"{'-' * 70}")
        print(result)

        # Print usage stats
        if response.usage:
            print(
                f"\n[Tokens - Prompt: {response.usage.prompt_tokens}, "
                f"Completion: {response.usage.completion_tokens}, "
                f"Total: {response.usage.total_tokens}]"
            )

        return result

    except Exception as e:
        print(f"\nError running test: {e}")
        return None


def main(expected_steps):
    """Main entry point."""
    args = parse_args()

    # List tests if requested
    if args.list:
        list_tests()
        return

    # Validate connection settings
    if not args.host:
        print("Error: Host not specified.")
        print("Use --host <IP> or set VLLM_ENDPOINT or VLLM_HOST environment variable.")
        print("\nExample:")
        print("  export VLLM_ENDPOINT='89.169.115.247:8000'")
        print("  python cosmos_reason2_tests.py")
        sys.exit(1)

    # Create client
    client = create_client(args.host, args.port, args.api_key)

    # Determine which tests to run
    if "all" in args.tests:
        tests_to_run = list(TESTS.keys())
    else:
        tests_to_run = args.tests

    print(f"\n{'#' * 70}")
    print(f"# Cosmos Reason 2 Prompt Tests")
    print(f"# Model: {args.model}")
    print(f"# Tests to run: {len(tests_to_run)}")
    print(f"{'#' * 70}")

    # Run tests
    result=[]
    results = {}
    for test_id in tests_to_run:
        if test_id in TESTS:
            result = run_test(client, args.model, test_id, TESTS[test_id])
            results[test_id] = {
                "name": TESTS[test_id]["name"],
                "success": result is not None,
                "response": result,
            }
        else:
            print(f"\nWarning: Unknown test '{test_id}', skipping.")

    # Print summary
    print(f"\n{'#' * 70}")
    print("# Summary")
    print(f"{'#' * 70}")

    successful = sum(1 for r in results.values() if r["success"])
    failed = len(results) - successful

    print(f"\nTotal tests: {len(results)}")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")

    if failed > 0:
        print("\nFailed tests:")
        for test_id, result in results.items():
            if not result["success"]:
                print(f"  - {test_id}: {result['name']}")

    print(f"\n{'#' * 70}")
    print("# Validation Report  ")
    print(f"{'#' * 70}\n")

    # ---------------------------------------------------------
    # RUN VALIDATION
    # ---------------------------------------------------------

    # paste the full response text (including <think> block) into response_text variable
    response_text = result

    think_text, missing, report = validate_think_against_expected(expected_steps, response_text)
    print(report)

    # json_text = extract_json_array(result)
    # events = json.loads(json_text)
    #
    # warnings = validate_steps(expected_steps, events)
    #
    # print("\nVALIDATION REPORT")
    # print("--------------------------------------------------")
    #
    # if not warnings:
    #     print("✔ All required steps are present. No compliance issues detected.")
    # else:
    #     for w in warnings:
    #         print(w)




# Minimal stopword set for keyword extraction
_STOPWORDS = {
    "the","and","or","to","of","a","an","in","on","for","with","by","is","are",
    "this","that","it","as","be","will","ensure","ensure","during","before",
    "after","then","into","from","at","using","used","use"
}

def _extract_think_block(text):
    """Return inner text of the first <think>...</think> block, or the original text if not found."""
    m = re.search(r"<think>(.*?)</think>", text, re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else text.strip()

def _keywords_from_definition(definition, min_len=4):
    """Simple keyword extractor: split on non-word chars, filter stopwords and short tokens."""
    tokens = re.findall(r"\w+", definition.lower())
    keywords = [t for t in tokens if len(t) >= min_len and t not in _STOPWORDS]
    # return unique keywords preserving order
    seen = set()
    out = []
    for k in keywords:
        if k not in seen:
            seen.add(k)
            out.append(k)
    return out

def validate_think_against_expected(expected_steps, response_text):
    """
    Extracts the <think> block from response_text, checks each expected step's definition
    for presence of keywords in the think text, and returns:
      (think_text, missing_steps_list, report_string)
    The report_string follows the compliance format requested.
    """
    think_text = _extract_think_block(response_text)
    normalized = think_text.lower()
    # remove punctuation for simpler substring checks
    normalized = normalized.translate(str.maketrans(string.punctuation, " " * len(string.punctuation)))
    missing = []

    for key, data in expected_steps.items():
        title = data.get("title", key)
        definition = data.get("definition", "")
        keywords = _keywords_from_definition(definition)
        # consider step found if any keyword appears as a whole word in normalized text
        found = False
        for kw in keywords:
            if re.search(r"\b" + re.escape(kw) + r"\b", normalized):
                found = True
                break
        if not found:
            missing.append({
                "key": key,
                "title": title,
                "definition": definition,
                "keywords_checked": keywords
            })

    # build report string
    if missing:
        # If multiple missing, list them all; user requested the specific message for Additional Surface Preparation
        report_lines = ["--------------------------------------------------"]
        for m in missing:
            report_lines.append(f"⚠️ MISSING STEP: **{m['title']}**")
            report_lines.append(f"   → Expected concepts NOT found in model output.")
            report_lines.append(f"   → Definition: {m['definition']}")
            report_lines.append(f"   → This step is compliance‑critical and MUST appear in the timeline.")
            report_lines.append("")  # blank line between entries
        report = "\n".join(report_lines).rstrip()
    else:
        report = "All expected steps present. Everything Good."

    return think_text, missing, report

# Example usage:
if __name__ == "__main__":
    # expected_steps as provided by the user (abbreviated here for example)
    expected_steps = {
        "1_Damage_Marking_and_Hole_Preparation": {
            "title": "Damage Marking and Hole Preparation",
            "definition": (
                "Identify dents on the wing surface and enlarge or align holes to prepare "
                "the repair zone for structural correction."
            )
        },

        "2_Surface_Cleaning_and_Corrosion_Removal": {
            "title": "Surface Cleaning and Corrosion Removal",
            "definition": (
                "Perform surface cleaning and corrosion removal before installing the new "
                "panel or patch, ensuring bare metal and proper surface treatment."
            )
        },

        "3_Additional_Surface_Preparation": {
            "title": "Additional Surface Preparation",
            "definition": (
                "Apply *alodine conversion coating*, approved primer, and a corrosion‑inhibiting "
                "compound (e.g., chromate‑based or non‑chromate equivalent) to the cleaned area; "
                "allow specified dwell times and cure cycles to ensure long‑term protection."
            )
        },

        "4_Patch_Plate_Installation": {
            "title": "Patch Plate Installation",
            "definition": (
                "Position the metal patch plate accurately over the treated area and secure "
                "it to maintain alignment during repair."
            )
        },

        "5_Panel_Shaping_and_Installation": {
            "title": "Panel Shaping and Installation",
            "definition": (
                "Refine the replacement panel for proper fit, then install it with sealant "
                "and secure it using approved rivet patterns and torque."
            )
        },

        "6_Final_Finish_and_Quality_Verification": {
            "title": "Final Finish and Quality Verification",
            "definition": (
                "Restore the surface with paint and conduct a final inspection to confirm "
                "structural integrity, alignment, and airworthiness."
            )
        },

        # NEW step added to force a validation failure
        "7_NDT_and_Bond_Verification": {
            "title": "Non Destructive Testing and Bond Verification",
            "definition": (
                "Perform non‑destructive testing (NDT) such as dye‑penetrant, ultrasonic, or "
                "eddy‑current inspections to verify crack absence and bond integrity. "
                "Conduct bond strength tests and torque verification on fasteners; document "
                "NDT reports and acceptance criteria before returning the aircraft to service."
            )
        }
    }
    main(expected_steps)

# if __name__ == "__main__":
#     # ---------------------------------------------------------
#     # EXPECTED STEPS (Your Provided Dictionary)
#     # ---------------------------------------------------------
#     expected_steps = {
#         "1_Damage_Marking_and_Hole_Preparation": {
#             "title": "Damage Marking and Hole Preparation",
#             "definition": (
#                 "Identify dents on the wing surface and enlarge or align holes to prepare "
#                 "the repair zone for structural correction."
#             )
#         },
#
#         "2_Surface_Cleaning_and_Corrosion_Removal": {
#             "title": "Surface Cleaning and Corrosion Removal",
#             "definition": (
#                 "Perform surface cleaning and corrosion removal before installing the new "
#                 "panel or patch, ensuring bare metal and proper surface treatment."
#             )
#         },
#
#         "3_Additional_Surface_Preparation": {
#             "title": "Additional Surface Preparation",
#             "definition": (
#                 "Apply approved primer, alodine, or corrosion‑inhibiting compound to the "
#                 "cleaned area to ensure long‑term structural protection."
#             )
#         },
#
#         "4_Patch_Plate_Installation": {
#             "title": "Patch Plate Installation",
#             "definition": (
#                 "Position the metal patch plate accurately over the treated area and secure "
#                 "it to maintain alignment during repair."
#             )
#         },
#
#         "5_Panel_Shaping_and_Installation": {
#             "title": "Panel Shaping and Installation",
#             "definition": (
#                 "Refine the replacement panel for proper fit, then install it with sealant "
#                 "and secure it using approved rivet patterns and torque."
#             )
#         },
#
#         "6_Final_Finish_and_Quality_Verification": {
#             "title": "Final Finish and Quality Verification",
#             "definition": (
#                 "Restore the surface with paint and conduct a final inspection to confirm "
#                 "structural integrity, alignment, and airworthiness."
#             )
#         }
#     }
#     main(expected_steps)
