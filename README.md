<p align="center">
  <img src="https://www.subconscious.dev/logo.svg" alt="Subconscious" width="64" height="64">
</p>

<h1 align="center">Subconscious Python SDK</h1>

<p align="center">
  The official Python SDK for the <a href="https://subconscious.dev">Subconscious API</a>
</p>

---

## Installation

```bash
pip install subconscious-sdk
```

## Quick start

```python
from subconscious import Subconscious, tools
from pydantic import BaseModel

client = Subconscious(api_key="...")

class Summary(BaseModel):
    summary: str
    score: float

run = client.run_and_wait(
    engine="tim-claude",
    input={
        "instructions": "Summarize and score this article: …",
        "tools": [tools.platform("parallel_search")],
        "answerFormat": Summary,  # Pydantic class — auto-converted
    },
)

print(run.result.answer)
```

## Three ways to start a run

### 1. Fire-and-forget — `client.run`

Returns the run with only `run_id` populated. Use this when a background
worker polls or when you've persisted the id and pick it up later.

```python
run = client.run(engine="tim-claude", input={"instructions": "Search AI news"})
db.insert({"run_id": run.run_id, "status": "queued"})
```

### 2. Block until done — `client.run_and_wait`

```python
run = client.run_and_wait(engine="tim-claude", input={"instructions": "Search AI news"})
print(run.result.answer)
```

### 3. Stream — `client.stream`

Yields typed events. The first event is always `StartedEvent`
(carrying `run_id`); the last is always `DoneEvent`. Exactly one
`ResultEvent` (success) or `ErrorEvent` (failure) fires before `done`.

```python
from subconscious.types import (
    DeltaEvent, StartedEvent, ResultEvent, ToolCallEvent, ErrorEvent,
)

for event in client.stream(engine="tim-claude", input={"instructions": "Write an essay"}):
    if isinstance(event, StartedEvent):
        print("run_id:", event.run_id)
    elif isinstance(event, DeltaEvent):
        print(event.content, end="", flush=True)
    elif isinstance(event, ToolCallEvent):
        print(f"\ntool: {event.call.tool_name} {event.call.parameters}")
    elif isinstance(event, ResultEvent):
        print("\nfinal answer:", event.result.answer)
    elif isinstance(event, ErrorEvent):
        print(f"[{event.code}] {event.message}")
```

## Re-attaching to a run — `client.observe`

Pick up a live or already-finished run and stream its events from the
durable buffer. Same wire format and event taxonomy as `stream()`.

```python
run = client.run(engine="tim-claude", input=...)
db.persist(run.run_id)

# … later, possibly in a different process:
for event in client.observe(run.run_id):
    if isinstance(event, ResultEvent):
        print(event.result.answer)
```

## Tools

```python
from subconscious import tools
from pydantic import BaseModel

class EmailArgs(BaseModel):
    to: str
    body: str

input = {
    "instructions": "Look up customers and send a follow-up email",
    "tools": [
        tools.platform("parallel_search"),
        tools.resource("sandbox"),
        tools.function(
            name="sendEmail",
            url="https://api.example.com/email",
            parameters=EmailArgs,             # Pydantic class — auto-converted
            defaults={"sender_id": "svc_abc"},  # hidden from model, auto-promoted
            headers={"Authorization": "Bearer xyz"},
        ),
        tools.mcp(
            url="https://mcp.example.com",
            headers={"Authorization": "Bearer xyz"},  # header-based auth
        ),
    ],
}
```

### Client-level FunctionTool overlays

```python
client = Subconscious(
    api_key="...",
    default_function_tool_headers={"Authorization": "Bearer xyz"},
    default_function_tool_defaults={"tenant_id": "t_abc"},
)
```

Per-tool values win on conflict.

## Structured output

Pass a Pydantic class directly — the SDK converts it for you:

```python
from pydantic import BaseModel

class Result(BaseModel):
    summary: str
    score: float

run = client.run_and_wait(
    engine="tim-claude",
    input={
        "instructions": "Rate this article",
        "answerFormat": Result,
    },
)

print(run.result.answer)  # already a dict matching Result; cast if needed
```

You can still pass a hand-built JSON Schema dict if you'd rather not
depend on Pydantic.

## Cancelling a run

`client.cancel(run_id)` is **idempotent**. Call it whether the run is
running, queued, or already terminal — it returns the run's current
shape. Only network / auth failures raise.

```python
run = client.run(engine="tim-claude", input=...)
client.cancel(run.run_id)  # safe regardless of state
client.cancel(run.run_id)  # also safe
```

## Error codes

Every `ErrorEvent` and every raised `SubconsciousError` carries a
canonical `code` from this set:

```
invalid_request  authentication_failed  permission_denied
not_found        rate_limited           internal_error
service_unavailable  timeout            cancelled
```

Pattern-match on `code`, never on `message`.

## Engines

The SDK accepts any engine name as a string. Canonical live names:

- `tim`, `tim-edge`
- `tim-claude`, `tim-claude-heavy`
- `tim-omni`, `tim-omni-mini`

Legacy names (`tim-large`, `tim-gpt`, `tim-small`, `timini`, …) are still
accepted and resolved to a live engine server-side.

## License

Apache-2.0. See `LICENSE`.
