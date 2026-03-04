import requests
HOSTPORT = "89.169.102.197:8000"  # NO scheme here
API_KEY = "wi8onM0ibKgB1clS"

# Choose http or https consistently:
SCHEME = "http"  # or "https" if TLS is configured

r = requests.get(f"{SCHEME}://{HOSTPORT}/health", timeout=10, verify=False if SCHEME=="https" else True)
print("Health:", r.status_code, r.text)

resp = requests.post(
    f"{SCHEME}://{HOSTPORT}/v1/chat/completions",
    headers={"Authorization": f"Bearer {API_KEY}"},
    json={
        "model": "nvidia/Cosmos-Reason2-2B",
        "messages": [{"role": "user", "content": "What is a robot?"}],
        "max_tokens": 128
    },
    timeout=60,
    verify=False if SCHEME=="https" else True
)
print(resp.status_code, resp.text)