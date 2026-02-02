import json
import logging
import inspect
from typing import List, Callable, Optional, Dict, Any, Union
from pydantic import BaseModel
import litellm

logger = logging.getLogger(__name__)

class AgentResponse(BaseModel):
    content: str

class LiteLLMAgent:
    def __init__(
        self,
        name: str,
        model: str,
        api_base: Optional[str] = None,
        api_key: Optional[str] = None,
        instructions: Optional[List[str]] = None,
        tools: Optional[List[Callable]] = None,
        debug_mode: bool = False,
        **kwargs
    ):
        self.name = name
        self.model = model
        self.api_base = api_base
        self.api_key = api_key
        self.instructions = instructions or []
        self.tools = tools or []
        self.debug_mode = debug_mode
        self.kwargs = kwargs
        
        self.tool_schemas = [self._function_to_schema(t) for t in self.tools]
        self.tool_map = {t.__name__: t for t in self.tools}

    def _function_to_schema(self, func: Callable) -> Dict[str, Any]:
        """
        Converts a function to an OpenAI tool schema.
        This is a simplified implementation and might need robustness.
        """
        sig = inspect.signature(func)
        doc = inspect.getdoc(func) or ""
        
        # Parse docstring for description
        description = doc.split("\n\n")[0] if doc else ""
        
        parameters = {
            "type": "object",
            "properties": {},
            "required": []
        }
        
        for name, param in sig.parameters.items():
            if name == "self":
                continue
                
            param_type = "string" # Default
            if param.annotation == int:
                param_type = "integer"
            elif param.annotation == bool:
                param_type = "boolean"
            # We treat Optional[...] as string usually unless specific check
            
            # Simple description extraction from docstring could be complex, 
            # here we skip detailed param descriptions for brevity unless we parse Google-style args
            
            parameters["properties"][name] = {
                "type": param_type,
                "description": f"Parameter {name}" 
            }
            
            if param.default == inspect.Parameter.empty:
                parameters["required"].append(name)
                
        return {
            "type": "function",
            "function": {
                "name": func.__name__,
                "description": description,
                "parameters": parameters
            }
        }

    async def arun(self, message: str, stream: bool = False) -> AgentResponse:
        messages = []
        if self.instructions:
            system_msg = "\n".join(self.instructions)
            messages.append({"role": "system", "content": system_msg})
        
        messages.append({"role": "user", "content": message})
        
        # Maximum turns to prevent infinite loops
        max_turns = 5
        current_turn = 0
        
        final_content = ""
        
        while current_turn < max_turns:
            current_turn += 1
            
            try:
                response = await litellm.acompletion(
                    model=self.model,
                    api_base=self.api_base,
                    api_key=self.api_key,
                    messages=messages,
                    tools=self.tool_schemas if self.tool_schemas else None,
                    tool_choice="auto" if self.tool_schemas else None,
                    stream=False # We handle streaming internally if needed, but for now blocking
                )
                
                from typing import cast, Any
                resp_obj = cast(Any, response)
                msg = resp_obj.choices[0].message
                messages.append(msg)
                
                if msg.tool_calls:
                    logger.info(f"Agent requested tool calls: {len(msg.tool_calls)}")
                    for tool_call in msg.tool_calls:
                        function_name = tool_call.function.name
                        arguments_str = tool_call.function.arguments
                        
                        if function_name in self.tool_map:
                            try:
                                arguments = json.loads(arguments_str)
                                tool_func = self.tool_map[function_name]
                                result = tool_func(**arguments)
                                
                                messages.append({
                                    "tool_call_id": tool_call.id,
                                    "role": "tool",
                                    "name": function_name,
                                    "content": str(result)
                                })
                            except Exception as e:
                                error_msg = f"Error executing {function_name}: {e}"
                                logger.error(error_msg)
                                messages.append({
                                    "tool_call_id": tool_call.id,
                                    "role": "tool",
                                    "name": function_name,
                                    "content": error_msg
                                })
                        else:
                            messages.append({
                                "tool_call_id": tool_call.id,
                                "role": "tool",
                                "name": function_name,
                                "content": f"Error: Tool {function_name} not found"
                            })
                    # Loop back to get response after tool output
                    continue
                
                # No tool calls, this is the final response
                final_content = msg.content
                break
                
            except Exception as e:
                error_str = str(e)
                logger.error(f"LiteLLM error: {error_str}")
                
                # Check for common connection errors
                if "Connection error" in error_str or "Connection refused" in error_str:
                    friendly_msg = (
                        f"Error: Could not connect to the LLM provider at {self.api_base or 'default location'}. "
                        "Please ensure the service is running and accessible."
                    )
                    return AgentResponse(content=friendly_msg)
                
                # Check for authentication errors
                if "AuthenticationError" in error_str or "api_key client option must be set" in error_str:
                     friendly_msg = (
                        "Error: Authentication failed. If using Llama.cpp via OpenAI-compatible API, "
                        "ensure an API key is provided (even if dummy like 'sk-no-key-required')."
                    )
                     return AgentResponse(content=friendly_msg)

                return AgentResponse(content=f"Error: {error_str}")
        
        return AgentResponse(content=final_content or "")
