"""Tool decorator and schema generation for Subconscious SDK.

Provides the @tool decorator for defining custom tool functions that the
Subconscious cloud agent can call via the dev server + tunnel.

Usage::

    from subconscious.tools import tool

    @tool
    def search(query: str) -> str:
        \"\"\"Search the web for information.\"\"\"
        return tavily.search(query)

    @tool(sandbox=E2BSandbox())
    def analyze(code: str) -> str:
        \"\"\"Run analysis in a cloud sandbox.\"\"\"
        return eval(code)
"""

import inspect
from typing import Any, Callable, Dict, List, Optional, get_type_hints

from subconscious.dev.mcp_proxy import MCPStdioServer

__all__ = ["tool", "MCPStdioServer"]

# Python type → JSON Schema type mapping
_TYPE_MAP = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
    bytes: "string",
}


def _python_type_to_json_schema(annotation: Any) -> Dict[str, Any]:
    """Convert a Python type annotation to a JSON Schema type."""
    if annotation is inspect.Parameter.empty or annotation is Any:
        return {"type": "string"}

    # Handle Optional[X] (Union[X, None])
    origin = getattr(annotation, "__origin__", None)
    args = getattr(annotation, "__args__", ())

    if origin is type(None):
        return {"type": "string"}

    # Optional[X] = Union[X, None]
    if _is_optional(annotation):
        inner = [a for a in args if a is not type(None)][0]
        return _python_type_to_json_schema(inner)

    # List[X]
    if origin is list:
        schema: Dict[str, Any] = {"type": "array"}
        if args:
            schema["items"] = _python_type_to_json_schema(args[0])
        return schema

    # Dict[K, V]
    if origin is dict:
        return {"type": "object"}

    # Direct type lookup
    if annotation in _TYPE_MAP:
        return {"type": _TYPE_MAP[annotation]}

    # Pydantic model
    if isinstance(annotation, type) and hasattr(annotation, "model_json_schema"):
        return annotation.model_json_schema()

    # Fallback
    return {"type": "string"}


def _is_optional(annotation: Any) -> bool:
    """Check if a type is Optional[X]."""
    origin = getattr(annotation, "__origin__", None)
    args = getattr(annotation, "__args__", ())
    # In Python 3.8+, Optional[X] is Union[X, None]
    if origin is not None and hasattr(origin, "__name__") and origin.__name__ == "Union":
        return type(None) in args
    # Also check typing.Union
    import typing
    if origin is typing.Union:
        return type(None) in args
    return False


def _generate_schema(func: Callable) -> Dict[str, Any]:
    """Generate a JSON Schema for a function's parameters.

    Uses inspect.signature() for parameter names/defaults and
    get_type_hints() for type annotations.
    """
    sig = inspect.signature(func)

    try:
        hints = get_type_hints(func)
    except Exception:
        hints = {}

    properties: Dict[str, Any] = {}
    required: List[str] = []

    for name, param in sig.parameters.items():
        if name in ("self", "cls"):
            continue

        annotation = hints.get(name, param.annotation)
        prop_schema = _python_type_to_json_schema(annotation)

        # Add description from docstring if parseable
        # (simple: just use the param name as implicit description)

        properties[name] = prop_schema

        # Required if no default and not Optional
        if param.default is inspect.Parameter.empty and not _is_optional(annotation):
            required.append(name)

    return {
        "type": "object",
        "properties": properties,
        "required": required,
    }


def tool(
    func: Optional[Callable] = None,
    *,
    sandbox: Optional[Any] = None,
    name: Optional[str] = None,
    description: Optional[str] = None,
) -> Any:
    """Decorator to define a custom tool function.

    The decorated function can be passed directly in the ``tools`` list
    to ``client.run()`` or ``client.stream()``. The SDK auto-generates
    a JSON Schema from the function's type hints and docstring.

    Args:
        func: The function to decorate (used when called without parens).
        sandbox: Optional sandbox backend instance. When provided, the
            function executes in the sandbox instead of locally.
        name: Override the tool name (defaults to function name).
        description: Override the tool description (defaults to docstring).

    Examples::

        @tool
        def search(query: str) -> str:
            \"\"\"Search the web.\"\"\"
            return do_search(query)

        @tool(name="db_query", description="Query the database")
        def query(sql: str) -> str:
            return db.execute(sql)

        @tool(sandbox=E2BSandbox())
        def analyze(code: str) -> str:
            \"\"\"Run in sandbox.\"\"\"
            return eval(code)
    """
    def decorator(f: Callable) -> Callable:
        f._subcon_tool = True  # type: ignore[attr-defined]
        f._subcon_sandbox = sandbox  # type: ignore[attr-defined]
        f._subcon_schema = _generate_schema(f)  # type: ignore[attr-defined]
        f._subcon_name = name or f.__name__  # type: ignore[attr-defined]
        f._subcon_description = description or f.__doc__ or ""  # type: ignore[attr-defined]
        return f

    if func is not None:
        # Called as @tool without parens
        return decorator(func)
    # Called as @tool(...) with parens
    return decorator
