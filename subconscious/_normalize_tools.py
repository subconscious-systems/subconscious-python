"""Pre-flight tool normalization (R9, R12).

Two responsibilities:

1. **Inject client-level FunctionTool overlays.** When the SDK was
   constructed with ``default_function_tool_headers`` /
   ``default_function_tool_defaults``, merge those into every FunctionTool.
   Per-tool values win on conflict so consumers can still override.

2. **Auto-promote ``defaults`` keys into the JSON Schema** (R12). Defaults
   are hidden values the engine never sees as model-controlled
   parameters, but the schema needs to declare them anyway so the engine
   can dispatch a complete payload. We synthesize a minimal property
   descriptor (``{"type": "string"}``) for each defaults-only key that is
   missing from ``parameters.properties``. Existing properties are left
   untouched.
"""

from dataclasses import asdict, is_dataclass
from typing import Any, Dict, List, Optional


def _to_dict(tool: Any) -> Dict[str, Any]:
    """Convert a tool dataclass / dict into a wire-format dict."""
    if isinstance(tool, dict):
        return {k: v for k, v in tool.items() if v is not None}
    if is_dataclass(tool):
        return {k: v for k, v in asdict(tool).items() if v is not None}
    if hasattr(tool, "__dict__"):
        return {k: v for k, v in tool.__dict__.items() if v is not None}
    return tool


def _infer_property_shape(value: Any) -> Dict[str, Any]:
    if isinstance(value, bool):
        return {"type": "boolean"}
    if isinstance(value, int) or isinstance(value, float):
        return {"type": "number"}
    if isinstance(value, list):
        return {"type": "array", "items": {"type": "string"}}
    if isinstance(value, dict):
        return {"type": "object"}
    return {"type": "string"}


def _promote_defaults(
    parameters: Optional[Dict[str, Any]],
    defaults: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Auto-promote defaults-only keys to ``parameters.properties``. (R12.)"""
    params: Dict[str, Any] = dict(parameters or {})
    if not defaults:
        return params

    if params.get("type") != "object":
        # Custom schema — leave it alone.
        return params

    properties = dict(params.get("properties") or {})
    mutated = False
    for key, value in defaults.items():
        if key not in properties:
            properties[key] = _infer_property_shape(value)
            mutated = True

    if not mutated:
        return parameters or {}

    params["properties"] = properties
    return params


def normalize_tools(
    tools: Optional[List[Any]],
    *,
    default_function_tool_headers: Optional[Dict[str, str]] = None,
    default_function_tool_defaults: Optional[Dict[str, Any]] = None,
) -> Optional[List[Dict[str, Any]]]:
    """Normalize a list of tools to the wire format the API expects."""
    if tools is None:
        return None

    out: List[Dict[str, Any]] = []
    for tool in tools:
        d = _to_dict(tool)
        if d.get("type") == "function":
            out.append(
                _normalize_function_tool(
                    d,
                    default_function_tool_headers,
                    default_function_tool_defaults,
                )
            )
        else:
            out.append(d)
    return out


def _normalize_function_tool(
    tool: Dict[str, Any],
    default_headers: Optional[Dict[str, str]],
    default_defaults: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Apply R9 overlays + R12 defaults promotion to a single function tool dict."""
    # Per-tool values win on conflict.
    merged_headers: Optional[Dict[str, str]]
    if default_headers or tool.get("headers"):
        merged_headers = {**(default_headers or {}), **(tool.get("headers") or {})}
    else:
        merged_headers = None

    merged_defaults: Optional[Dict[str, Any]]
    if default_defaults or tool.get("defaults"):
        merged_defaults = {**(default_defaults or {}), **(tool.get("defaults") or {})}
    else:
        merged_defaults = None

    parameters = _promote_defaults(tool.get("parameters"), merged_defaults)

    new_tool: Dict[str, Any] = {**tool, "parameters": parameters}
    if merged_headers:
        new_tool["headers"] = merged_headers
    elif "headers" in new_tool and not merged_headers:
        new_tool.pop("headers", None)
    if merged_defaults:
        new_tool["defaults"] = merged_defaults
    return new_tool
