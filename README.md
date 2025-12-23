<p align="center">
  <img src="https://www.subconscious.dev/logo.svg" alt="Subconscious" width="64" height="64">
</p>

<h1 align="center">Subconscious SDK</h1>

<p align="center">
  The official Python SDK for the <a href="https://subconscious.dev">Subconscious API</a>
</p>

<p align="center">
  <a href="https://pypi.org/project/subconscious-sdk/"><img src="https://img.shields.io/pypi/v/subconscious-sdk.svg" alt="PyPI version"></a>
  <a href="https://pypi.org/project/subconscious-sdk/"><img src="https://img.shields.io/pypi/dm/subconscious-sdk.svg" alt="PyPI downloads"></a>
  <a href="https://docs.subconscious.dev"><img src="https://img.shields.io/badge/docs-subconscious.dev-blue" alt="docs"></a>
  <img src="https://img.shields.io/badge/python-%3E%3D3.8-brightgreen" alt="python version">
  <a href="https://github.com/subconscious-systems/subconscious-sdk"><img src="https://img.shields.io/pypi/l/subconscious-sdk.svg" alt="license"></a>
</p>

---

## Installation

```bash
pip install subconscious-python
# or
uv add subconscious-python
# or
poetry add subconscious-python
```

> **Note**: The package name is `subconscious-python` but you import it as `subconscious`.

## Quick Start

```python
from subconscious import Subconscious

client = Subconscious(api_key="your-api-key")

run = client.run(
    engine="tim-large",
    input={
        "instructions": "Search for the latest AI news and summarize the top 3 stories",
        "tools": [{"type": "platform", "id": "parallel_search"}],
    },
    options={"await_completion": True},
)

print(run.result.answer)
```

## Get Your API Key

Create an API key in the [Subconscious dashboard](https://www.subconscious.dev/platform).

## Usage

### Run and Wait

The simplest way to use the SDK—create a run and wait for completion:

```python
run = client.run(
    engine="tim-large",
    input={
        "instructions": "Analyze the latest trends in renewable energy",
        "tools": [{"type": "platform", "id": "parallel_search"}],
    },
    options={"await_completion": True},
)

print(run.result.answer)
print(run.result.reasoning)  # Structured reasoning nodes
```

### Fire and Forget

Start a run without waiting, then check status later:

```python
run = client.run(
    engine="tim-large",
    input={
        "instructions": "Generate a comprehensive report",
        "tools": [],
    },
)

print(f"Run started: {run.run_id}")

# Check status later
status = client.get(run.run_id)
print(status.status)  # 'queued' | 'running' | 'succeeded' | 'failed' | 'canceled' | 'timed_out'
```

### Poll with Custom Options

```python
run = client.run(
    engine="tim-large",
    input={
        "instructions": "Complex task",
        "tools": [{"type": "platform", "id": "parallel_search"}],
    },
)

# Wait with custom polling options
result = client.wait(
    run.run_id,
    options={
        "interval_ms": 2000,  # Poll every 2 seconds
        "max_attempts": 60,   # Give up after 60 attempts
    },
)
```

### Streaming (Text Deltas)

Stream text as it's generated:

```python
for event in client.stream(
    engine="tim-large",
    input={
        "instructions": "Write a short essay about space exploration",
        "tools": [{"type": "platform", "id": "parallel_search"}],
    },
):
    if event.type == "delta":
        print(event.content, end="", flush=True)
    elif event.type == "done":
        print(f"\n\nRun completed: {event.run_id}")
    elif event.type == "error":
        print(f"Error: {event.message}")
```

> **Note**: Rich streaming events (reasoning steps, tool calls) are coming soon. Currently, the stream provides text deltas as they're generated.

### Tools

```python
# Platform tools (hosted by Subconscious)
parallel_search = {
    "type": "platform",
    "id": "parallel_search",
}

# Function tools (your own functions)
custom_function = {
    "type": "function",
    "name": "get_weather",
    "description": "Get current weather for a location",
    "parameters": {
        "type": "object",
        "properties": {
            "location": {"type": "string"},
        },
        "required": ["location"],
    },
    "url": "https://api.example.com/weather",
    "method": "GET",
    "timeout": 30,
}

# MCP tools
mcp_tool = {
    "type": "mcp",
    "url": "https://mcp.example.com",
    "allow": ["read", "write"],
}
```

### Error Handling

```python
from subconscious import (
    Subconscious,
    SubconsciousError,
    AuthenticationError,
    RateLimitError,
)

try:
    run = client.run(...)
except AuthenticationError:
    print("Invalid API key")
except RateLimitError:
    print("Rate limited, retry later")
except SubconsciousError as e:
    print(f"API error: {e.code} - {e}")
```

### Cancellation

```python
# Cancel a running run
client.cancel(run.run_id)
```

## API Reference

### `Subconscious`

The main client class.

#### Constructor Options

| Option     | Type   | Required | Default                           |
| ---------- | ------ | -------- | --------------------------------- |
| `api_key`  | `str`  | Yes      | -                                 |
| `base_url` | `str`  | No       | `https://api.subconscious.dev/v1` |

#### Methods

| Method                      | Description              |
| --------------------------- | ------------------------ |
| `run(engine, input, options)` | Create a new run       |
| `stream(engine, input)`     | Stream text deltas       |
| `get(run_id)`               | Get run status           |
| `wait(run_id, options)`     | Poll until completion    |
| `cancel(run_id)`            | Cancel a running run     |

### Engines

| Engine              | Type     | Availability | Description                                                       |
| ------------------- | -------- | ------------ | ----------------------------------------------------------------- |
| `tim-small-preview` | Unified  | Available    | Fast and tuned for search tasks                                   |
| `tim-large`         | Compound | Available    | Generalized reasoning engine backed by the power of OpenAI        |
| `timini`            | Compound | Coming soon  | Generalized reasoning engine backed by the power of Google Gemini |

### Run Status

| Status      | Description            |
| ----------- | ---------------------- |
| `queued`    | Waiting to start       |
| `running`   | Currently executing    |
| `succeeded` | Completed successfully |
| `failed`    | Encountered an error   |
| `canceled`  | Manually canceled      |
| `timed_out` | Exceeded time limit    |

## Requirements

- Python ≥ 3.8
- requests

## Contributing

Contributions are welcome! Please feel free to submit a pull request.

## License

Apache-2.0

## Support

For support and questions:
- Documentation: https://docs.subconscious.dev
- Email: {hongyin,jack}@subconscious.dev
