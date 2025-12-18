import json
import requests

from openai import OpenAI
from typing import List, Dict, Type, Union, Tuple, Optional, get_origin, get_args

from .tim_api import tim_streaming
from .grammar import Tool, Task, BaseTask, create_thread_grammar


class ToolKit:
    def __init__(self, tools: Dict[str, Type]=None):
        self.toolmap = tools or {}
        self.tools_raw = {}
    
    def update_tools(
            self, 
            toolkit_name: str = 'default', 
            new_tools: Dict[str, Type] = None,
            tools: List[Dict] = None
        ):
        self.toolmap[toolkit_name] = new_tools
        self.tools_raw[toolkit_name] = tools


class TaskManager:
    def __init__(self):
        self.omni_task_dict = {}
    
    def set_omni_task(self, omni_task_name: str, omni_task_model: Type):
        self.omni_task_dict[omni_task_name] = omni_task_model


class ThreadManager:
    def __init__(self):
        self.thread_dict = {
            'default/default': create_thread_grammar(
                reasoning_type=List[BaseTask],
                answer_type=str
            )
        }
    
    def set_thread(self, thread_name: str, thread_model: Type):
        self.thread_dict[thread_name] = thread_model
    
    def get_thread(self, thread_name: str = 'default'):
        return self.thread_dict.get(thread_name)


class Agent:
    def __init__(self, openai_client):
        self.openai_client = openai_client
        self.toolkit = ToolKit()
        self.thread_map = ThreadManager()
    
    def parse(
            self,
            messages: List[Dict[str, str]],
            model: str = 'tim-large',
            tools: List[Dict] = None,
            reasoning_schema: Type = None
        ):

        return tim_streaming(
            self.openai_client,
            model=model,  # Adjust model as needed
            messages=messages,
            tools=tools,
            reasoning_grammar_model=reasoning_schema
        )
    
    def run(
            self,
            messages: List[Dict[str, str]],
            agent_name: str = 'default',
            thread_name: str = 'default',
            model: str = 'tim-large'
        ):
        tools = self.toolkit.tools_raw.get(agent_name, [])
        thread_schema = self.thread_map.get_thread(f'{agent_name}/{thread_name}')
        
        return tim_streaming(
            self.openai_client,
            messages=messages,
            model=model,
            tools=list(tools),
            reasoning_grammar_model=thread_schema
        )


class Client:

    def __init__(self, base_url: str = "https://api.subconscious.dev/v1", api_key: str = None):
        openai_client = OpenAI(
            base_url=base_url, api_key=api_key
        )
        self.agent = Agent(openai_client)
        self.task_manager = TaskManager()
        self.BaseTask = BaseTask

    def get_hosted_tools(self, org_name: str = None, toolkit: str = 'all'):
        pass

    def build_toolkit(
            self,
            tools: List[Dict],
            agent_name: str = 'default',
            answer_model: Type = str,
            web_sync: bool = False
        ):
        """
        tools: List of tool definitions
        web_sync: Whether to sync the toolkit with the web service
        """
        toolkit, OmniTask = Tool.create_toolkit_with_task(
            tools, task_name=agent_name
        )

        self.agent.toolkit.update_tools(agent_name, toolkit, tools)
        self.agent.thread_map.set_thread(
            f'{agent_name}/default',
            create_thread_grammar(
                reasoning_type=List[OmniTask],
                answer_type=answer_model
            )
        )
        self.task_manager.set_omni_task(agent_name, OmniTask)
    
    def check_task_array(self, task_model, task_title):
        if task_model is not None:
            origin = get_origin(task_model)
            
            # Check if it's a direct List or Tuple
            if origin in (list, tuple):
                pass  # Valid
            # Check if it's a Union
            elif origin is Union:
                union_args = get_args(task_model)
                # Verify all union members are List or Tuple
                for arg in union_args:
                    arg_origin = get_origin(arg)
                    if arg_origin not in (list, tuple):
                        raise TypeError(
                            f"Invalid {task_title} type: {task_model}. "
                            f"Only List[...], Tuple[...], or Union[List[...], Tuple[...], ...] are accepted."
                        )
            else:
                raise TypeError(
                    f"Invalid {task_title} type: {task_model}. "
                    f"Only List[...], Tuple[...], or Union[List[...], Tuple[...], ...] are accepted."
                )
    
    def create_task(
            self,
            task_name: str,
            agent_name: str = 'default',
            thought: str = None,
            tools: Union[Tuple[str], List[str]] = None,
            subtasks: Type = None,
            flex: bool = False
        ) -> Type:
        
        if type(tools) is str:
            tools = (tools, )
        
        # Type guard for subtasks - only accept List[...], Tuple[...], or Union[List[], Tuple[], ...]
        self.check_task_array(subtasks, 'subtasks')
        
        agent_toolkit = self.agent.toolkit.toolmap.get(agent_name, {})
        agent_tool_subset = tuple(agent_toolkit[tool_name] for tool_name in tools) if tools else None
        
        task_model = Task.create(
            task_name,
            thought=thought,
            tools=agent_tool_subset,
            subtasks=subtasks,
            flex=flex
        )
        return task_model

    def set_thread(self, agent_name: str, thread_name: str, thread_model: Type):
        self.agent.thread_map.set_thread(f'{agent_name}/{thread_name}', thread_model)
    
    def create_thread(
            self,
            reasoning_model: Type,
            answer_model: Type = str,
            agent_name: str = 'default',
            thread_name: str = 'default'
        ) -> Type:
        self.check_task_array(reasoning_model, 'reasoning_model')
        
        thread_model = create_thread_grammar(
            reasoning_type=reasoning_model,
            answer_type=answer_model
        )
        self.set_thread(agent_name, thread_name, thread_model)
        return thread_model

