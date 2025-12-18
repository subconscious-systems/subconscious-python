"""
Subconscious Python SDK

A Python SDK for the Subconscious AI agent framework, providing structured reasoning
and tool integration capabilities.
"""

from .client import Client, Agent, ToolKit, TaskManager, ThreadManager
from .grammar import Tool, Task, BaseTask, create_thread_grammar
from .tim_api import TIMResponse, tim_streaming

__version__ = "0.1.21"
__author__ = "Subconscious Systems"
__email__ = "contact@subconscious.dev"

__all__ = [
    "Client",
    "Agent", 
    "ToolKit",
    "TaskManager",
    "ThreadManager",
    "Tool",
    "Task", 
    "BaseTask",
    "create_thread_grammar",
    "TIMResponse",
    "tim_streaming",
]

