import json
import re

# -------------------------------------------------------------------
# RAW MODEL RESPONSE (your exact input)
# -------------------------------------------------------------------

# -------------------------------------------------------------------
# STEP 1 — Extract JSON block safely
# -------------------------------------------------------------------
def extract_json_array(text):
    # Extract content inside ```json ... ```
    match = re.search(r"```json(.*?)```", text, re.DOTALL)
    if not match:
        raise ValueError("No JSON block found.")

    json_text = match.group(1).strip()

    # Fix broken ending: replace ]" with ]
    json_text = json_text.replace(']"', ']')

    return json_text


# -------------------------------------------------------------------
# STEP 2 — Expected 6-step instruction dictionary
# -------------------------------------------------------------------

# -------------------------------------------------------------------
# STEP 3 — Extract keywords from definitions
# -------------------------------------------------------------------
def extract_keywords(definition):
    words = re.findall(r"[a-zA-Z]+", definition.lower())
    stopwords = {"the", "and", "or", "to", "for", "with", "a", "of", "on", "it", "then"}
    return [w for w in words if w not in stopwords]


# -------------------------------------------------------------------
# STEP 4 — Validate model output against expected steps
# -------------------------------------------------------------------
def validate_steps(expected, events):
    warnings = []

    combined_text = " ".join([e["caption"].lower() for e in events])

    for step_key, step_data in expected.items():
        title = step_data["title"]
        definition = step_data["definition"]
        keywords = extract_keywords(definition)

        found = any(keyword in combined_text for keyword in keywords)

        if not found:
            warnings.append(
                f"\n⚠️ MISSING STEP: **{title}**\n"
                f"   → Expected concepts NOT found in model output.\n"
                f"   → Definition: {definition}\n"
                f"   → This step is compliance‑critical and MUST appear in the timeline.\n"
            )

    return warnings


# -------------------------------------------------------------------
# STEP 5 — Execute validation
# -------------------------------------------------------------------
