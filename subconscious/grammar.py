from pydantic import BaseModel, Field, create_model
from typing import Any, Dict, Literal, Tuple, Type, Union, List, Optional


class ConfiguredBase(BaseModel):
    model_config = {
        "arbitrary_types_allowed": True,
    }


def underscore_to_camel(tool_name: str) -> str:
    if tool_name is None:
        return None
    components = tool_name.split('_') + ['Tool']
    return ''.join(x.title() for x in components)


def create_task_with_depth(task_name: str, depth: int, tools: Tuple[Type[BaseModel], ...] = None, thought = None) -> Type[BaseModel]:
    if depth < 1:
        raise ValueError("Depth must be at least 1")
    
    if thought is None:
        top_lv_thought = (str, ...)
    else:
        top_lv_thought = (Literal[thought], ...)
    
    if tools is not None:
        if depth == 1:
            task_model_no_rec = create_model(
                task_name,
                thought=top_lv_thought,
                tooluse=(Optional[Union[tools]], ...) if tools else None,
                conclusion=(str, ...),
            )
            return task_model_no_rec
        
        else:
            task_model_no_rec = create_model(
                task_name + f'LV{depth}',
                thought=(str, ...),
                tooluse=(Optional[Union[tools]], ...) if tools else None,
                conclusion=(str, ...),
            )
            subtask_models = [task_model_no_rec]
            for i in range(depth - 1, 1, -1):
                subtask_models.append(create_model(
                    f"{task_name}LV{i}",
                    thought=(str, ...),
                    tooluse=(Optional[Union[tools]], ...) if tools else None,
                    subtasks=(Optional[List[subtask_models[-1]]], ...),
                    conclusion=(str, ...),
                ))
            
            task_model = create_model(
                task_name,
                thought=top_lv_thought,
                tooluse=(Optional[Union[tools]], ...) if tools else None,
                subtasks=(Optional[List[subtask_models[-1]]], ...),
                conclusion=(str, ...),
            )
            task_model.model_rebuild()
            
            return task_model
    else:
        if depth == 1:
            task_model_no_rec = create_model(
                task_name,
                thought=top_lv_thought,
                conclusion=(str, ...),
            )
            return task_model_no_rec
        
        else:
            task_model_no_rec = create_model(
                task_name + f'LV{depth}',
                thought=(str, ...),
                conclusion=(str, ...),
            )
            subtask_models = [task_model_no_rec]

            for i in range(depth - 1, 1, -1):
                # print(f"{task_name}LV{i}")
                subtask_models.append(create_model(
                    f"{task_name}LV{i}",
                    thought=(str, ...),
                    subtasks=(Optional[List[
                        subtask_models[-1]
                    ]], ...),
                    conclusion=(str, ...),
                ))
            
            task_model = create_model(
                task_name,
                thought=top_lv_thought,
                subtasks=(Optional[List[subtask_models[-1]]], ...),
                conclusion=(str, ...),
            )
            task_model.model_rebuild()
            
            return task_model

BaseTask = create_task_with_depth('BaseTask', depth=3)


class Tool:
    
    @classmethod
    def type_map(cls, t) -> Type:
        type_map = {
            "string": str,
            "boolean": bool,
            "number": float,
            "integer": int,
            "null": type(None)
        }
        if type(t) == str:
            return type_map.get(t, Any)
        elif type(t) == dict:
            # for example: {"type": "array", "items": {"type": "string"}}
            if t.get("type") == "array":
                item_type = cls.type_map(t.get("items", {}).get("type", "any"))
                return List[item_type]
        return Any
    
    @classmethod
    def create_tool_param_model(cls, tool_name: str, parameters: Dict[str, Dict]) -> Type[BaseModel]:
        param_fields = {}
        for name, spec in parameters['properties'].items():
            # print(spec)

            # If type is a list, combine using Optional
            if 'anyOf' in spec:
                annotation = Optional[cls.type_map(spec['anyOf'][0])]
                # default = None
            else:
                t = spec["type"]

                if isinstance(t, list):
                    py_type = next((cls.type_map(x) for x in t if x != "null"), str)
                    annotation = Optional[py_type]
                    # default = None
                else:
                    annotation = cls.type_map(t)
                    # default = ... if t != "null" else None
            param_fields[name] = (annotation, Field(..., description=spec.get("description", "")))
        
        ParamModel = create_model(
            f'{tool_name}Params',
            **param_fields
        )
        return ParamModel

    @classmethod
    def create_toolkit_with_task(cls, tools: List[Dict[str, Any]], task_name: str = None) -> Tuple[Dict[str, Type[BaseModel]], Type[BaseModel]]:
        tool_registry = {}
        tool_model_list = []

        for tool in tools:
            tool_name = tool['name']
            # print(tool_name)
            parameters = tool['parameters']
            
            literal_tool_name = underscore_to_camel(tool_name)
            tool_model = create_model(
                literal_tool_name,
                tool_name=(Literal[tool_name], ...),
                parameters=(cls.create_tool_param_model(literal_tool_name, parameters), ...),
                tool_result=(Any, ...)
            )
            tool_registry[tool_name] = tool_model
            tool_model_list.append(tool_model)
        
        # OmniTask = create_model(
        #     underscore_to_camel(task_name) or 'OmniTask',
        #     title=(str, ...),
        #     thought=(str, ...),
        #     tooluse=(Optional[Union[tuple(tool_model_list)]], ...),
        #     subtasks=(Optional[List[
        #         underscore_to_camel(task_name) or 'OmniTask'
        #     ]], ...),
        #     conclusion=(str, ...),
        # )
        OmniTask = create_task_with_depth(
            task_name=underscore_to_camel(task_name) or 'OmniTask',
            depth=3,
            tools=tuple(tool_model_list)
        )
        # Resolve forward references for self-referential 'subtasks'
        OmniTask.model_rebuild()
        
        return tool_registry, OmniTask


class Task:
    
    def create(
            task_name,
            thought=None,
            tools=None,
            subtasks=None,
            depth: int = 1,
            flex=False
        ) -> BaseModel:
        # task_model = create_model(
        #     task_name,
        #     # title=(str, ...) if title is None else (Literal[title], ...),
        #     thought=(str, ...) if thought is None else (Literal[thought], ...),
        #     tooluse=(Union[tools], ...) if tools else None,
        #     subtasks=subtasks if subtasks else None,
        #     conclusion=(str, ...),
        # )
        
        if flex and tools is None:
            return BaseTask
        
        elif flex:
            task = create_task_with_depth(task_name, depth=5, tools=tools, thought=thought)
            return task

        if tools is None and subtasks is None:
            task_model = create_task_with_depth(task_name, depth=depth, thought=thought)

        elif tools is None and subtasks is not None:
            task_model = create_model(
                task_name,
                thought=(str, ...) if thought is None else (Literal[thought], ...),
                # tooluse=(Union[tools], ...) if tools else None,
                subtasks=subtasks,
                conclusion=(str, ...),
            )

        elif tools is not None and subtasks is None:
            task_model = create_model(
                task_name,
                thought=(str, ...) if thought is None else (Literal[thought], ...),
                tooluse=(Union[tools], ...),
                # subtasks=subtasks if subtasks else None,
                conclusion=(str, ...),
            )
        
        else:
            task_model = create_model(
                task_name,
                thought=(str, ...) if thought is None else (Literal[thought], ...),
                tooluse=(Union[tools], ...) if tools else None,
                subtasks=(subtasks, ...) if subtasks else None,
                conclusion=(str, ...),
            )

        return task_model


def create_thread_grammar(reasoning_type, answer_type):
    return create_model(
        'thread',
        reasoning=(reasoning_type, ...),
        answer=(answer_type, ...)
    )

