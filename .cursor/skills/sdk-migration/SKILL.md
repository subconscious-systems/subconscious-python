---
name: sdk-migration
description: >-
  Migration guide for breaking changes between subconscious-sdk versions.
  Use when upgrading the SDK, fixing import errors after upgrade, or when
  the user encounters removed types like ModelUsage or PlatformToolUsage.
---

# SDK Migration Guide

## Migrating from 0.x to 1.0

Version 1.0 aligns the Python SDK's response types with the API wire format.
Response models are now Pydantic `BaseModel` instances instead of dataclasses,
and their fields match the JSON returned by the Subconscious API 1:1.

### Summary of breaking changes

- `Usage` is now a flat Pydantic model (`input_tokens`, `output_tokens`, `duration_ms`). The old `models` and `platform_tools` fields are removed.
- `ModelUsage` and `PlatformToolUsage` are deleted entirely.
- `ReasoningNode` is removed. Use `ReasoningTask` instead.
- `ReasoningTask.subtask` is renamed to `subtasks`.
- `ReasoningTask.tooluse` is now `Optional[AgentToolUse]` instead of `List[Any]`.
- `RunResult.reasoning` is now `Optional[List[ReasoningTask]]` instead of `Optional[ReasoningNode]`.
- `Run` has a new `error: Optional[RunError]` field for failed runs.
- `Run`, `RunResult`, `Usage`, `RunError`, `ReasoningTask`, and `AgentToolUse` are Pydantic `BaseModel` instead of `@dataclass`.
- `Engine` literal expanded: added `"tim-edge"`, `"tim-oss-local"`, `"tim-1.5"`, `"tim-gpt-heavy-tc"`.

### Usage — before and after

```python
# 0.x — broken; models/platform_tools were raw dicts, not dataclass instances
run.usage.models[0].input_tokens
run.usage.platform_tools[0].tool_id

# 1.0 — flat, matches API wire format
run.usage.input_tokens    # int
run.usage.output_tokens   # int
run.usage.duration_ms     # Optional[int]
```

### ReasoningTask — before and after

```python
# 0.x
from subconscious import ReasoningNode
node.subtask       # List[ReasoningNode]
node.tooluse       # List[Any]

# 1.0 — ReasoningNode is removed
from subconscious import ReasoningTask
task.subtasks      # Optional[List[ReasoningTask]]
task.tooluse       # Optional[AgentToolUse]
task.tooluse.tool_name       # str
task.tooluse.tool_call_id    # Optional[str]
task.tooluse.parameters      # Dict[str, Any]
task.tooluse.tool_result     # Optional[Any]
```

### RunResult.reasoning — before and after

```python
# 0.x — single node
run.result.reasoning  # Optional[ReasoningNode]

# 1.0 — list of tasks (matches API)
run.result.reasoning  # Optional[List[ReasoningTask]]
for task in run.result.reasoning or []:
    print(task.title, task.thought)
```

### Run.error — new field

```python
# 1.0 — error details on failed runs
if run.status == "failed" and run.error:
    print(f"Error {run.error.code}: {run.error.message}")
```

### Removed exports

```python
# 0.x — these imports will fail in 1.0
from subconscious import ModelUsage       # REMOVED
from subconscious import PlatformToolUsage  # REMOVED
from subconscious import ReasoningNode    # REMOVED

# 1.0 — new exports
from subconscious import AgentToolUse
from subconscious import RunError
from subconscious import ReasoningTask
```

### Dataclass to Pydantic

Attribute access is unchanged (`run.run_id`, `run.usage.input_tokens`), but
`isinstance` checks and construction patterns differ:

```python
# 0.x
from dataclasses import is_dataclass
assert is_dataclass(run)

# 1.0
from pydantic import BaseModel
assert isinstance(run, BaseModel)

# Construction still works the same way:
run = Run(run_id="run_abc", status="queued")
```

### Engine literal

```python
# 0.x
Engine = Literal["tim", "tim-claude", "tim-claude-heavy"]

# 1.0
Engine = Literal[
    "tim", "tim-edge", "tim-claude", "tim-claude-heavy",
    "tim-oss-local", "tim-1.5", "tim-gpt-heavy-tc",
]
```

### Quick find-and-replace patterns

| Old pattern | Replacement |
|---|---|
| `from subconscious import ModelUsage` | Remove — no longer exists |
| `from subconscious import PlatformToolUsage` | Remove — no longer exists |
| `from subconscious import ReasoningNode` | `from subconscious import ReasoningTask` |
| `run.usage.models` | `run.usage.input_tokens` / `run.usage.output_tokens` |
| `run.usage.platform_tools` | Remove — no longer exists |
| `.subtask` (on ReasoningTask) | `.subtasks` |
| `ReasoningNode` (in type hints/code) | `ReasoningTask` |
| `run.result.reasoning.title` | `run.result.reasoning[0].title` (now a list) |
| `RunInput(..., reasoning_format=...)` | Remove — field no longer exists |
| `{'reasoningFormat': ...}` | Remove — field no longer exists |

## `reasoning_format` removed

The `reasoning_format` input field (aliased as `reasoningFormat` on the wire) is gone. If you were shaping the reasoning trace with a JSON/Pydantic schema, fold that guidance into your `instructions` or into `answer_format` instead — the agent's final output is the contract, and the reasoning trace is best treated as a read-only byproduct.

```python
# Before
client.run(
    engine='tim',
    input={
        'instructions': '...',
        'answerFormat': AnswerSchema,
        'reasoningFormat': ReasoningSchema,
    },
)

# After
client.run(
    engine='tim',
    input={
        'instructions': '...',
        'answerFormat': AnswerSchema,
    },
)
```

Requests that still include `reasoningFormat` are rejected by the API.

## `RunResult.parsed_answer`

`result.answer` is always a `str` on the wire, even when `answerFormat` is supplied — the API JSON-encodes the structured value. The SDK now attaches a `parsed_answer` companion field on every response that runs through the client (`run`, `get`, `wait`, `cancel`), populated via a best-effort `json.loads` of `answer`.

```python
from pydantic import BaseModel

class Person(BaseModel):
    name: str
    age: int

run = client.run(
    engine='tim',
    input={
        'instructions': 'return JSON for a person',
        'answerFormat': Person,
    },
    options={'await_completion': True},
)

run.result.answer         # '{"name":"ada","age":36}'  (raw string)
run.result.parsed_answer  # {'name': 'ada', 'age': 36}  (decoded dict)
```

`parsed_answer` is typed as `Any` — validate with your Pydantic model of choice (`Person.model_validate(run.result.parsed_answer)`) if you want a typed instance. It is `None` when `answer` is empty or not valid JSON.
