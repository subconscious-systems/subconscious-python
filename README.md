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
pip install subconscious-sdk
# or
uv add subconscious-sdk
# or
poetry add subconscious-sdk
```

> **Note**: The package name is `subconscious-sdk` but you import it as `subconscious`.

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

### Structured Output

Get responses in a specific JSON schema format using Pydantic models:

```python
from pydantic import BaseModel
from subconscious import Subconscious

class AnalysisResult(BaseModel):
    summary: str
    key_points: list[str]
    sentiment: str

client = Subconscious(api_key="your-api-key")

run = client.run(
    engine="tim-large",
    input={
        "instructions": "Analyze the latest news about electric vehicles",
        "tools": [{"type": "platform", "id": "parallel_search"}],
        "answerFormat": AnalysisResult,  # Pass the Pydantic class directly
    },
    options={"await_completion": True},
)

# The answer will conform to your schema
print(run.result.answer)  # JSON string matching AnalysisResult
```

The SDK automatically converts your Pydantic model to JSON Schema. You can also pass a raw JSON Schema dict if preferred.

For advanced use cases, you can also specify a `reasoningFormat` to structure the agent's reasoning output.

### Tools

```python
# Platform tools (hosted by Subconscious)
parallel_search = {
    "type": "platform",
    "id": "parallel_search",
}

# Function tools (your own HTTP endpoints)
custom_function = {
    "type": "function",
    "name": "get_weather",
    "description": "Get current weather for a location",
    "url": "https://api.example.com/weather",
    "method": "GET",
    "timeout": 30,
    "parameters": {
        "type": "object",
        "properties": {
            "location": {"type": "string"},
        },
        "required": ["location"],
    },
}

# MCP tools
mcp_tool = {
    "type": "mcp",
    "url": "https://mcp.example.com",
    "allow": ["read", "write"],
}
```

### Tool Headers & Default Arguments

Function tools support two powerful features for injecting data at call time:

- **`headers`**: HTTP headers sent with the request to your tool endpoint
- **`defaults`**: Parameter values hidden from the model and injected automatically

```python
tool_with_headers_and_defaults = {
    "type": "function",
    "name": "search_database",
    "description": "Search the database",
    "url": "https://api.example.com/search",
    "method": "POST",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            # Define these for validation, but they'll be hidden from the model
            "session_id": {"type": "string"},
            "api_key": {"type": "string"},
        },
        "required": ["query"],  # Only query is required - model generates this
    },
    
    # HEADERS: Sent as HTTP headers when this tool's endpoint is called
    "headers": {
        "x-custom-auth": "my-secret-token",
        "x-request-source": "my-app",
    },
    
    # DEFAULTS: Injected into parameters, hidden from model
    "defaults": {
        "session_id": "user-session-abc123",
        "api_key": "secret-api-key",
    },
}
```

**How it works:**

| Feature | Where it goes | When |
|---------|---------------|------|
| `headers` | HTTP request headers | Sent to your tool's URL |
| `defaults` | Merged into request body `parameters` | At tool call time |

**Default arguments flow:**
1. Define all parameters in `properties` (required for validation)
2. Parameters with defaults are **stripped from the schema** before the model sees them
3. Model only generates values for non-defaulted parameters (e.g., `query`)
4. At call time, defaults are merged into the request body
5. Default values always take precedence over model-generated values

Each tool can have its own headers and defaults - they're only applied when that specific tool is called.

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
