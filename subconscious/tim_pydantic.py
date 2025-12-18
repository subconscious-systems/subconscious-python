from __future__ import annotations

import json
import copy
import inspect
import humps

from typing import Optional, List, Literal, Union, Any, Iterable, cast, TYPE_CHECKING, TypeVar
from typing_extensions import TypeGuard, override

import pydantic
from pydantic import BaseModel
from pydantic.v1.typing import (
    get_args as get_args,
    is_union as is_union,
    get_origin as get_origin,
    is_typeddict as is_typeddict,
    is_literal_type as is_literal_type,
)
from pydantic.v1.datetime_parse import parse_date as parse_date, parse_datetime as parse_datetime

GenericModel = BaseModel

PYDANTIC_V2 = pydantic.VERSION.startswith("2.")

_T = TypeVar("_T")

# Sentinel class used until PEP 0661 is accepted
class NotGiven:
    """
    A sentinel singleton class used to distinguish omitted keyword arguments
    from those passed in with the value None (which may have different behavior).

    For example:

    ```py
    def get(timeout: Union[int, NotGiven, None] = NotGiven()) -> Response: ...


    get(timeout=1)  # 1s timeout
    get(timeout=None)  # No timeout
    get()  # Default timeout behavior, which may not be statically known at the method definition.
    ```
    """

    def __bool__(self) -> Literal[False]:
        return False

    @override
    def __repr__(self) -> str:
        return "NOT_GIVEN"


NotGivenOr = Union[_T, NotGiven]
NOT_GIVEN = NotGiven()

def captial_first_letter(word):
    return f'{word[0].upper()}{word[1:]}'

def get_title(phrase):
    if '_' in phrase:
        word_list = phrase.split('_')
    else:
        word_list = humps.decamelize(phrase).split('_')
    return ' '.join([captial_first_letter(x) for x in word_list])

def is_dataclass_like_type(typ: type) -> bool:
    """Returns True if the given type likely used `@pydantic.dataclass`"""
    return hasattr(typ, "__pydantic_config__")

def is_basemodel_type(type_: type) -> TypeGuard[type[BaseModel] | type[GenericModel]]:
    origin = get_origin(type_) or type_
    if not inspect.isclass(origin):
        return False
    return issubclass(origin, BaseModel) or issubclass(origin, GenericModel)


def class_about_tool(d):
    name_path = d['$ref']
    return 'Tool' in name_path


def add_tool_to_schema(schema, tool_name, tool_info):
    param_name = f'{tool_name}Param'
    # schema['json_schema']['schema']['$defs'].pop('CodingToolParam')
    # toolcall_schema = schema['json_schema']['schema']['$defs'].pop('CodingTool')
    toolcall_schema = copy.deepcopy(schema['json_schema']['schema']['$defs']['CodingTool'])

    toolcall_schema['title'] = tool_name
    toolcall_schema['properties']['tool_name']['const'] = tool_name
    toolcall_schema['properties']['parameters']['$ref'] = f"#/$defs/{param_name}"

    tool_params = tool_info.parameters
    tool_params['title'] = param_name
    
    for k, v in tool_params['properties'].items():
        param_title = get_title(k)
        tool_params['properties'][k]['title'] = param_title
    
    schema['json_schema']['schema']['$defs'][param_name] = tool_params
    schema['json_schema']['schema']['$defs'][tool_name] = toolcall_schema
    return schema


def add_tool_to_claude(schema, tool_name, tool_info):
    param_name = f'{tool_name}Param'
    # schema['json_schema']['schema']['$defs'].pop('CodingToolParam')
    # toolcall_schema = schema['json_schema']['schema']['$defs'].pop('CodingTool')
    toolcall_schema = copy.deepcopy(schema['input_schema']['$defs']['CodingTool'])

    toolcall_schema['title'] = tool_name
    toolcall_schema['properties']['tool_name']['const'] = tool_name
    toolcall_schema['properties']['parameters']['$ref'] = f"#/$defs/{param_name}"

    tool_params = tool_info.parameters
    tool_params['title'] = param_name
    
    for k, v in tool_params['properties'].items():
        param_title = get_title(k)
        tool_params['properties'][k]['title'] = param_title
    
    schema['input_schema']['$defs'][param_name] = tool_params
    schema['input_schema']['$defs'][tool_name] = toolcall_schema
    return schema


def get_custom_tool_schema(response_format, sampling_params):
    schema = type_to_response_format_param(response_format)
    tools = sampling_params.tool_dict

    if tools is None:
        schema['json_schema']['schema']['properties']['action']['anyOf'] = [
            x for x in schema['json_schema']['schema']['properties']['action']['anyOf'] if not\
                class_about_tool(x)
        ]
        if 'EraseToolResult' in schema['json_schema']['schema']['$defs']:
            schema['json_schema']['schema']['$defs'].pop('EraseToolResult')

        schema['json_schema']['schema']['$defs'].pop('CodingToolParam')
        schema['json_schema']['schema']['$defs'].pop('CodingTool')
        schema['json_schema']['schema']['$defs'].pop('ToolCall')
        return schema
    
    for tool_name, tool_info in tools.items():
        schema = add_tool_to_schema(schema, tool_name, tool_info)
    
    schema['json_schema']['schema']['$defs'].pop('CodingToolParam')
    schema['json_schema']['schema']['$defs'].pop('CodingTool')
    
    tool_name_list = [
        f'#/$defs/{x}' for x in tools.keys()
    ]
    if len(tool_name_list) == 1:
        schema['json_schema']['schema']['$defs']['ToolCall']['properties']['tool'] = {
            '$ref': tool_name_list[0]
        }
    else:
        schema['json_schema']['schema']['$defs']['ToolCall']['properties']['tool'] = {
            'anyOf': [
                {'$ref': x} for x in tool_name_list
            ]
        }
    
    return schema


def get_claude_tool_schema(response_format, sampling_params):
    schema = response_format
    tools = sampling_params.tool_dict
    
    for tool_name, tool_info in tools.items():
        schema = add_tool_to_claude(schema, tool_name, tool_info)
    
    schema['input_schema']['$defs'].pop('CodingToolParam')
    schema['input_schema']['$defs'].pop('CodingTool')

    tool_name_list = [
        f'#/$defs/{x}' for x in tools.keys()
    ]
    if len(tool_name_list) == 1:
        schema['input_schema']['properties']['tool'] = {
            '$ref': tool_name_list[0]
        }
    else:
        schema['input_schema']['properties']['tool'] = {
            'anyOf': [
                {'$ref': x} for x in tool_name_list
            ]
        }
    
    return schema


def get_custom_json_schema(response_format, sampling_params):
    schema = type_to_response_format_param(response_format)
    if sampling_params.response_format is None:
        return schema

    custom_schema = sampling_params.response_format['json_schema']    
    name = custom_schema['name']
    properties = custom_schema['schema']['properties']
    required = custom_schema['schema'].get('required', [])
    title = custom_schema['schema'].get('title', name)
    
    for k, v in custom_schema['schema']['$defs'].items():
        if k not in schema['json_schema']['schema']['$defs']:
            schema['json_schema']['schema']['$defs'][k] = v
    
    schema['json_schema']['schema']['$defs'][name] = {
        'type': 'object',
        'title': title,
        'properties': properties,
        'required': required,
        'additionalProperties': False,
    }
    
    schema['json_schema']['schema']['$defs']['Conclude']['properties']['final_answer'] = {
        '$ref': f"#/$defs/{name}"
    }
    return schema


def get_claude_json_schema(response_format, sampling_params):
    # schema = type_to_response_format_param(response_format)
    schema = response_format
    if sampling_params.response_format is None:
        return schema
    
    schema[-1]['input_schema']['$defs'] = {}

    custom_schema = sampling_params.response_format['json_schema']    
    name = custom_schema['name']
    properties = custom_schema['schema']['properties']
    required = custom_schema['schema'].get('required', [])
    title = custom_schema['schema'].get('title', name)
    
    for k, v in custom_schema['schema']['$defs'].items():
        if k not in schema[-1]['input_schema']['$defs']:
            schema[-1]['input_schema']['$defs'][k] = v

    schema[-1]['input_schema']['$defs'][name] = {
        'type': 'object',
        'title': title,
        'properties': properties,
        'required': required,
        'additionalProperties': False,
    }

    schema[-1]['input_schema']['properties']['final_answer'] = {
        '$ref': f"#/$defs/{name}"
    }
    return schema
    

def type_to_response_format_param(
    response_format):

    # type checkers don't narrow the negation of a `TypeGuard` as it isn't
    # a safe default behaviour but we know that at this point the `response_format`
    # can only be a `type`
    response_format = cast(type, response_format)

    json_schema_type: type[pydantic.BaseModel] | pydantic.TypeAdapter[Any] | None = None

    if is_basemodel_type(response_format):
        name = response_format.__name__
        json_schema_type = response_format
    elif is_dataclass_like_type(response_format):
        name = response_format.__name__
        json_schema_type = pydantic.TypeAdapter(response_format)
    else:
        raise TypeError(f"Unsupported response_format type - {response_format}")

    return {
        "type": "json_schema",
        "json_schema": {
            "schema": to_strict_json_schema(json_schema_type),
            "name": name,
            "strict": True,
        },
    }


def _is_dict(obj: object) -> TypeGuard[dict[object, object]]:
    return isinstance(obj, dict)


def is_list(obj: object) -> TypeGuard[list[object]]:
    return isinstance(obj, list)


def model_json_schema(model):
    if PYDANTIC_V2:
        return model.model_json_schema()
    return model.schema()  # pyright: ignore[reportDeprecated]


def to_strict_json_schema(model: type[pydantic.BaseModel] | pydantic.TypeAdapter[Any]) -> dict[str, Any]:
    if inspect.isclass(model) and is_basemodel_type(model):
        schema = model_json_schema(model)
    elif PYDANTIC_V2 and isinstance(model, pydantic.TypeAdapter):
        schema = model.json_schema()
    else:
        raise TypeError(f"Non BaseModel types are only supported with Pydantic v2 - {model}")

    return _ensure_strict_json_schema(schema, path=(), root=schema)


def _ensure_strict_json_schema(
    json_schema: object,
    *,
    path: tuple[str, ...],
    root: dict[str, object],
) -> dict[str, Any]:
    """Mutates the given JSON schema to ensure it conforms to the `strict` standard
    that the API expects.
    """
    if not is_dict(json_schema):
        raise TypeError(f"Expected {json_schema} to be a dictionary; path={path}")

    defs = json_schema.get("$defs")
    if is_dict(defs):
        for def_name, def_schema in defs.items():
            _ensure_strict_json_schema(def_schema, path=(*path, "$defs", def_name), root=root)

    definitions = json_schema.get("definitions")
    if is_dict(definitions):
        for definition_name, definition_schema in definitions.items():
            _ensure_strict_json_schema(definition_schema, path=(*path, "definitions", definition_name), root=root)

    typ = json_schema.get("type")
    if typ == "object" and "additionalProperties" not in json_schema:
        json_schema["additionalProperties"] = False

    # object types
    # { 'type': 'object', 'properties': { 'a':  {...} } }
    properties = json_schema.get("properties")
    if is_dict(properties):
        json_schema["required"] = [prop for prop in properties.keys()]
        json_schema["properties"] = {
            key: _ensure_strict_json_schema(prop_schema, path=(*path, "properties", key), root=root)
            for key, prop_schema in properties.items()
        }

    # arrays
    # { 'type': 'array', 'items': {...} }
    items = json_schema.get("items")
    if is_dict(items):
        json_schema["items"] = _ensure_strict_json_schema(items, path=(*path, "items"), root=root)

    # unions
    any_of = json_schema.get("anyOf")
    if is_list(any_of):
        json_schema["anyOf"] = [
            _ensure_strict_json_schema(variant, path=(*path, "anyOf", str(i)), root=root)
            for i, variant in enumerate(any_of)
        ]

    # intersections
    all_of = json_schema.get("allOf")
    if is_list(all_of):
        if len(all_of) == 1:
            json_schema.update(_ensure_strict_json_schema(all_of[0], path=(*path, "allOf", "0"), root=root))
            json_schema.pop("allOf")
        else:
            json_schema["allOf"] = [
                _ensure_strict_json_schema(entry, path=(*path, "allOf", str(i)), root=root)
                for i, entry in enumerate(all_of)
            ]

    # strip `None` defaults as there's no meaningful distinction here
    # the schema will still be `nullable` and the model will default
    # to using `None` anyway
    if json_schema.get("default", NOT_GIVEN) is None:
        json_schema.pop("default")

    # we can't use `$ref`s if there are also other properties defined, e.g.
    # `{"$ref": "...", "description": "my description"}`
    #
    # so we unravel the ref
    # `{"type": "string", "description": "my description"}`
    ref = json_schema.get("$ref")
    if ref and has_more_than_n_keys(json_schema, 1):
        assert isinstance(ref, str), f"Received non-string $ref - {ref}"

        resolved = resolve_ref(root=root, ref=ref)
        if not is_dict(resolved):
            raise ValueError(f"Expected `$ref: {ref}` to resolved to a dictionary but got {resolved}")

        # properties from the json schema take priority over the ones on the `$ref`
        json_schema.update({**resolved, **json_schema})
        json_schema.pop("$ref")
        # Since the schema expanded from `$ref` might not have `additionalProperties: false` applied,
        # we call `_ensure_strict_json_schema` again to fix the inlined schema and ensure it's valid.
        return _ensure_strict_json_schema(json_schema, path=path, root=root)

    return json_schema


def resolve_ref(*, root: dict[str, object], ref: str) -> object:
    if not ref.startswith("#/"):
        raise ValueError(f"Unexpected $ref format {ref!r}; Does not start with #/")

    path = ref[2:].split("/")
    resolved = root
    for key in path:
        value = resolved[key]
        assert is_dict(value), f"encountered non-dictionary entry while resolving {ref} - {resolved}"
        resolved = value

    return resolved


def is_basemodel_type(typ: type) -> TypeGuard[type[pydantic.BaseModel]]:
    if not inspect.isclass(typ):
        return False
    return issubclass(typ, pydantic.BaseModel)


def is_dataclass_like_type(typ: type) -> bool:
    """Returns True if the given type likely used `@pydantic.dataclass`"""
    return hasattr(typ, "__pydantic_config__")


def is_dict(obj: object) -> TypeGuard[dict[str, object]]:
    # just pretend that we know there are only `str` keys
    # as that check is not worth the performance cost
    return _is_dict(obj)


def has_more_than_n_keys(obj: dict[str, object], n: int) -> bool:
    i = 0
    for _ in obj.keys():
        i += 1
        if i > n:
            return True
    return False

