# Python SDK Quickstart

Demonstrates the **v2 Helios SDK** (`Helios.configure`): manual agent /
retrieval / tool spans plus a deterministic OpenAI call captured by automatic
instrumentation, exported through authenticated OTLP/HTTP protobuf to
`/v1/otlp/traces`.

The OpenAI call uses a **mock HTTP transport** — it exercises the real OpenAI
client and the official instrumentor with no network access and no paid request.
Prompt/response content is **not** captured unless you opt in (see Privacy).

## Setup (from repo root)

```bash
python3 -m venv examples/python_sdk_quickstart/.venv
source examples/python_sdk_quickstart/.venv/bin/activate
pip install -r examples/python_sdk_quickstart/requirements.txt
```

## Create a key and export it

Backend must have migration `003_project_api_keys` applied. From `backend/`
(with `DATABASE_URL` set and its venv active):

```bash
python -m app.cli.api_keys create \
  --project-slug sdk-quickstart \
  --project-name "SDK Quickstart" \
  --environment development \
  --name "Local development" \
  --scopes traces:ingest,traces:read
export HELIOS_API_KEY=hel_proj_xxxxxxxxxxxxxxxx_...
```

## Run

```bash
python examples/python_sdk_quickstart/main.py --api-url http://localhost:8000
```

Prints the emitted 32-hex `trace_id` (never the key) and, if the key has
`traces:read`, the persisted service name and span list. Expected spans:
`support-agent` (root), `knowledge_base.search`, `lookup_policy`, and the
auto-instrumented `chat gpt-4o-mini` — all under one trace.

## Minimal real-application snippet

For a real app, drop the mock transport and use your real OpenAI client. Do
**not** commit your keys.

```python
import os
from helios_sdk import Helios
from openai import OpenAI

helios = Helios.configure(
    api_key=os.environ["HELIOS_API_KEY"],
    service_name="my-agent",
    # endpoint defaults to http://localhost:8000; set HELIOS_ENDPOINT in prod
)
helios.instrument_openai()  # content capture OFF by default

client = OpenAI()  # uses OPENAI_API_KEY; base URL unchanged

with helios.agent("my-agent"):
    with helios.retrieval("kb.search") as span:
        span.set_attribute("retrieval.top_k", 5)
    client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "..."}],
    )

helios.force_flush()   # before a short-lived process exits
helios.shutdown()
```

## Privacy

Prompt and completion content are **disabled by default**. Enabling capture
(`HELIOS_CAPTURE_CONTENT=true` or `helios.instrument_openai(capture_content=True)`)
sends message content to Helios. You are responsible for consent, redaction, and
data-handling requirements. API keys are secrets — never commit them or ship
them in browser code.
