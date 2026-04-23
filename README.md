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
  <img src="https://img.shields.io/badge/python-%3E%3D3.10-brightgreen" alt="python version">
  <a href="https://github.com/subconscious-systems/subconscious-sdk"><img src="https://img.shields.io/pypi/l/subconscious-sdk.svg" alt="license"></a>
</p>

---

## Installation

```bash
uv add subconscious-sdk
# or
pip install subconscious-sdk
```

> **Note**: The package name is `subconscious-sdk` but you import it as `subconscious`.

## Quick Start

```python
from subconscious import Subconscious

client = Subconscious(api_key="your-api-key")

run = client.run(
    engine="tim-claude",
    input={
        "instructions": "Search for the latest AI news and summarize the top 3 stories",
        "tools": [{"type": "platform", "id": "fast_search"}],
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
    engine="tim-claude",
    input={
        "instructions": "Analyze the latest trends in renewable energy",
        "tools": [{"type": "platform", "id": "fast_search"}],
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
    engine="tim-claude",
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
    engine="tim-claude",
    input={
        "instructions": "Complex task",
        "tools": [{"type": "platform", "id": "fast_search"}],
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
    engine="tim-claude",
    input={
        "instructions": "Write a short essay about space exploration",
        "tools": [{"type": "platform", "id": "fast_search"}],
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

### Skills

Attach reusable knowledge packages to your runs. Skills use progressive disclosure: the agent sees a summary in its system prompt and loads full instructions on demand.

```python
run = client.run(
    engine="tim-claude",
    input={
        "instructions": "Build a REST API following our team standards",
        "tools": [{"type": "platform", "id": "web_search"}],
        "skills": ["api-design", "error-handling"],
    },
    options={"await_completion": True},
)
```

Skills are resolved by name. You can browse and create skills at [subconscious.dev/platform/skills](https://www.subconscious.dev/platform/skills) or via the [Skills API](https://docs.subconscious.dev/core-concepts/skills).

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
    engine="tim-claude",
    input={
        "instructions": "Analyze the latest news about electric vehicles",
        "tools": [{"type": "platform", "id": "fast_search"}],
        "answerFormat": AnalysisResult,  # Pass the Pydantic class directly
    },
    options={"await_completion": True},
)

# The answer will conform to your schema
print(run.result.answer)  # JSON string matching AnalysisResult
```

The SDK automatically converts your Pydantic model to JSON Schema. You can also pass a raw JSON Schema dict if preferred.

### Multimodal Input (Images)

Send images alongside text instructions using the `Image` helper:

```python
from subconscious import Subconscious, Image

client = Subconscious(api_key="your-api-key")

# From a local file
run = client.run(
    engine="tim-claude",
    input={
        "instructions": "Describe what you see in this image",
        "content": [Image.from_path("photo.png")],
    },
    options={"await_completion": True},
)

print(run.result.answer)
```

`Image` supports several sources:

```python
# From a URL (server-side fetch)
Image.from_url("https://example.com/photo.jpg")

# From a URL (client-side fetch, embeds as base64)
Image.from_url("https://example.com/photo.jpg", fetch=True)

# From raw bytes
Image.from_bytes(image_bytes)

# From a previously uploaded blob
Image.from_blob_ref(blob_key="abc123", mime="image/png")
```

Supported formats: PNG, JPEG, GIF, and WebP.

### Image Tool Responses

If you have a function tool that generates or fetches an image, return it as a `ToolResponse` with mixed text and image content. The agent will see the image and can reason about it. This is useful for tools that generate images, such as a screenshot tool for computer use.

```python
from subconscious import ToolResponse, Image

# Your tool endpoint receives a tool_call_id from the agent.
# Return an image alongside text using ToolResponse.build():
response = ToolResponse.build(
    tool_call_id="call_abc123",
    content=[
        "Here is the generated chart:",
        Image.from_path("chart.png"),
    ],
)

# Or from a URL
response = ToolResponse.build(
    tool_call_id="call_abc123",
    content=[
        "Screenshot captured successfully.",
        Image.from_url("https://example.com/screenshot.png"),
    ],
)
```

`ToolResponse.build()` accepts a string, a single content block, or a mixed list of strings and `Image` blocks — it normalizes everything into the wire format automatically. You can use this when building custom tools to use with Subconscious.

### Tools

**Platform tools** — Hosted search and retrieval tools like `fast_search`, `web_search`, `news_search`, and more. See the [tools documentation](https://docs.subconscious.dev/core-concepts/tools) for the full list.

```python
# Platform tools (hosted by Subconscious)
fast_search = {
    "type": "platform",
    "id": "fast_search",
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

# MCP tools (connect to any MCP server)
mcp_tool = {
    "type": "mcp",
    "url": "https://mcp.example.com",
    "allowedTools": ["search", "get_page"],
}
```

### Tool Headers & Default Arguments

Function tools support two powerful features for injecting data at call time:

- `**headers**`: HTTP headers sent with the request to your tool endpoint
- `**defaults**`: Parameter values hidden from the model and injected automatically

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


| Feature    | Where it goes                         | When                    |
| ---------- | ------------------------------------- | ----------------------- |
| `headers`  | HTTP request headers                  | Sent to your tool's URL |
| `defaults` | Merged into request body `parameters` | At tool call time       |


**Default arguments flow:**

1. Define all parameters in `properties` (required for validation)
2. Parameters with defaults are **stripped from the schema** before the model sees them
3. Model only generates values for non-defaulted parameters (e.g., `query`)
4. At call time, defaults are merged into the request body
5. Default values always take precedence over model-generated values

Each tool can have its own headers and defaults - they're only applied when that specific tool is called.

### MCP Tools

Connect to any [Model Context Protocol](https://modelcontextprotocol.io/) server and use its tools in your runs. Subconscious discovers tools from the server, filters by your `allowedTools` list, and proxies calls automatically.

#### Authentication

MCP servers that require authentication accept an `auth` object. The auth translates to an HTTP header sent with every tool call:


| Method      | When to use                            | Header sent                                                                          |
| ----------- | -------------------------------------- | ------------------------------------------------------------------------------------ |
| **Bearer**  | Most common — OAuth tokens, JWTs, etc. | `Authorization: Bearer <token>`                                                      |
| **API key** | Service-specific API keys              | `<header>: <token>` (header is typically `X-Api-Key` — check your MCP server's docs) |


```python
from subconscious import Subconscious, MCPTool, McpAuth

client = Subconscious()

# Basic — use all tools from an MCP server
run = client.run(
    engine="tim-claude",
    input={
        "instructions": "Find my recent meeting notes",
        "tools": [
            MCPTool(url="https://mcp.notion.so/v1"),
        ],
    },
    options={"await_completion": True},
)

# Filter to specific tools
run = client.run(
    engine="tim-claude",
    input={
        "instructions": "Search my documents",
        "tools": [
            MCPTool(
                url="https://mcp.notion.so/v1",
                allowed_tools=["search", "get_page"],  # case-insensitive
            ),
        ],
    },
    options={"await_completion": True},
)

# With bearer auth (most common — e.g. OAuth tokens)
# → sends header: { "Authorization": "Bearer <token>" }
run = client.run(
    engine="tim-claude",
    input={
        "instructions": "Check my calendar",
        "tools": [
            MCPTool(
                url="https://mcp.google.com/v1",
                auth=McpAuth(type="bearer", token="your-oauth-token"),
            ),
        ],
    },
    options={"await_completion": True},
)

# API key auth with custom header
# → sends header: { "X-Api-Key": "<token>" }
# The header name is typically "X-Api-Key" but may vary —
# check the docs of the MCP server you are connecting to.
run = client.run(
    engine="tim-claude",
    input={
        "instructions": "Query the database",
        "tools": [
            MCPTool(
                url="https://mcp.example.com",
                auth=McpAuth(type="api_key", token="key123", header="X-Api-Key"),
            ),
        ],
    },
    options={"await_completion": True},
)
```

`**allowedTools` filtering:**


| Value                 | Behavior                              |
| --------------------- | ------------------------------------- |
| Omitted / `None`      | All tools from the server are enabled |
| `["*"]`               | All tools enabled (explicit wildcard) |
| `["search", "fetch"]` | Only these tools (case-insensitive)   |
| `[]`                  | No tools (blocks all)                 |


You can also pass MCP tools as plain dicts:

```python
{"type": "mcp", "url": "https://mcp.example.com", "allowedTools": ["search"]}
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

### Webhooks

Get a POST when runs complete instead of polling.

**Per-run callback**: pass `callbackUrl` on any run:

```python
run = client.run(
    engine="tim-claude",
    input={"instructions": "Generate a report"},
    output={"callbackUrl": "https://your-server.com/webhook"},
)
```

**Org-wide subscriptions**: receive webhooks for all runs. Manage in the [dashboard](https://www.subconscious.dev/platform/webhooks) or via the API:

```bash
curl -X POST https://api.subconscious.dev/v1/webhooks/subscriptions \
  -H "Authorization: Bearer $SUBCONSCIOUS_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "callbackUrl": "https://your-server.com/webhook",
    "eventTypes": ["job.succeeded", "job.failed"],
    "secret": "your-signing-secret"
  }'
```

Subscriptions support enable/disable, HMAC-SHA256 signing, and a delivery log. See the [webhooks docs](https://docs.subconscious.dev/core-concepts/async-webhooks) for more.

### Cancellation

```python
# Cancel a running run
client.cancel(run.run_id)
```

## API Reference

See the full [API documentation](https://docs.subconscious.dev) for detailed reference. The `Subconscious` client exposes five core methods: `run()`, `stream()`, `get()`, `wait()`, and `cancel()`.

For available engines and pricing, see the [pricing page](https://docs.subconscious.dev/pricing).

A run's `status` field is one of: `queued`, `running`, `succeeded`, `failed`, `canceled`, or `timed_out`.


## Development

We recommend [uv](https://docs.astral.sh/uv/) as your package manager. See `pyproject.toml` for Python version requirements and dependencies.

## Upgrading

If you're upgrading from 0.x, see the
[Migration Guide](https://github.com/subconscious-systems/subconscious-python/blob/main/.cursor/skills/sdk-migration/SKILL.md)
for breaking changes and code examples.

## Contributing

Contributions are welcome! Please feel free to submit a pull request.

## Support

For support and questions:

- Documentation: [https://docs.subconscious.dev](https://docs.subconscious.dev)
- Email: {hongyin,jack,dana,wei}@subconscious.dev

