import json
import logging
import inspect
import re
import types
from typing import List, Callable, Optional, Dict, Any, Union, cast, get_args, get_origin
from pydantic import BaseModel
import litellm

from opentelemetry import trace
from sidestage.tracing.middleware import add_trace_event, record_error

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("sidestage.agent")

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
        tools: Optional[List[Callable[..., Any]]] = None,
        debug_mode: bool = False,
        **kwargs: Any
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

    @staticmethod
    def _resolve_json_type(annotation: Any) -> str:
        """Map a Python type annotation to a JSON Schema type string."""
        # Unwrap Optional / union types (e.g. int | None, Optional[str])
        origin = get_origin(annotation)
        if origin is Union or origin is types.UnionType:
            args = [a for a in get_args(annotation) if a is not type(None)]
            if args:
                annotation = args[0]

        if annotation is int:
            return "integer"
        if annotation is float:
            return "number"
        if annotation is bool:
            return "boolean"
        return "string"

    @staticmethod
    def _parse_docstring_args(doc: str) -> Dict[str, str]:
        """Parse Google-style Args section from a docstring.

        Returns a mapping of parameter name → description.
        """
        params: Dict[str, str] = {}
        in_args = False
        current_name: str | None = None
        current_desc: list[str] = []

        for line in doc.splitlines():
            stripped = line.strip()
            # Detect start of Args block
            if stripped in ("Args:", "Arguments:"):
                in_args = True
                continue
            # Detect end of Args block (next section header)
            if in_args and stripped and not stripped.startswith(" ") and stripped.endswith(":"):
                if re.match(r"^[A-Z][a-z]+:$", stripped):
                    break

            if not in_args:
                continue

            # New parameter line: "name: description" or "name (type): description"
            m = re.match(r"^(\w+)(?:\s*\([^)]*\))?\s*:\s*(.*)", stripped)
            if m:
                if current_name is not None:
                    params[current_name] = " ".join(current_desc).strip()
                current_name = m.group(1)
                current_desc = [m.group(2)] if m.group(2) else []
            elif current_name is not None and stripped:
                # Continuation line
                current_desc.append(stripped)

        if current_name is not None:
            params[current_name] = " ".join(current_desc).strip()
        return params

    def _function_to_schema(self, func: Callable[..., Any]) -> Dict[str, Any]:
        """Converts a function to an OpenAI tool schema."""
        sig = inspect.signature(func)
        doc = inspect.getdoc(func) or ""

        # First paragraph is the tool description
        description = doc.split("\n\n")[0] if doc else ""
        arg_docs = self._parse_docstring_args(doc)

        parameters: Dict[str, Any] = {
            "type": "object",
            "properties": {},
            "required": [],
        }

        for name, param in sig.parameters.items():
            if name == "self":
                continue

            param_type = self._resolve_json_type(param.annotation)
            param_desc = arg_docs.get(name, f"Parameter {name}")

            parameters["properties"][name] = {
                "type": param_type,
                "description": param_desc,
            }

            if param.default == inspect.Parameter.empty:
                parameters["required"].append(name)

        return {
            "type": "function",
            "function": {
                "name": func.__name__,
                "description": description,
                "parameters": parameters,
            },
        }

    async def arun(self, message: str, context: str | None = None, stream: bool = False) -> AgentResponse:
        with tracer.start_as_current_span("agent.run") as span:
            span.set_attribute("agent.name", self.name)
            span.set_attribute("gen_ai.request.model", self.model)

            messages = []
            if self.instructions:
                system_msg = "\n".join(self.instructions)
                messages.append({"role": "system", "content": system_msg})

            if context:
                messages.append({"role": "system", "content": context})

            messages.append({"role": "user", "content": message})

            max_turns = 5
            current_turn = 0
            total_input_tokens = 0
            total_output_tokens = 0
            final_content = ""

            while current_turn < max_turns:
                current_turn += 1

                with tracer.start_as_current_span("llm.completion") as llm_span:
                    llm_span.set_attribute("agent.turn", current_turn)

                    add_trace_event("gen_ai.prompt", {
                        "role": "system",
                        "content": "\n".join(self.instructions) if self.instructions else "",
                    })
                    add_trace_event("gen_ai.prompt", {
                        "role": "user",
                        "content": message,
                    })

                    try:
                        response = await litellm.acompletion(
                            model=self.model,
                            api_base=self.api_base,
                            api_key=self.api_key,
                            messages=messages,
                            tools=self.tool_schemas if self.tool_schemas else None,
                            tool_choice="auto" if self.tool_schemas else None,
                            max_tokens=200,
                            stream=False,
                        )

                        resp_obj = cast(Any, response)
                        msg = resp_obj.choices[0].message

                        add_trace_event("gen_ai.completion", {
                            "content": msg.content or "",
                        })

                        # Extract token usage
                        usage = getattr(resp_obj, 'usage', None)
                        if usage:
                            input_tokens = getattr(usage, 'prompt_tokens', 0) or 0
                            output_tokens = getattr(usage, 'completion_tokens', 0) or 0
                            llm_span.set_attribute("gen_ai.usage.input_tokens", input_tokens)
                            llm_span.set_attribute("gen_ai.usage.output_tokens", output_tokens)
                            total_input_tokens += input_tokens
                            total_output_tokens += output_tokens

                        llm_span.set_attribute("gen_ai.response.finish_reasons",
                            [choice.finish_reason for choice in resp_obj.choices])

                        messages.append(msg)

                        if msg.tool_calls:
                            logger.info(f"Agent requested tool calls: {len(msg.tool_calls)}")
                            for tool_call in msg.tool_calls:
                                function_name = tool_call.function.name
                                arguments_str = tool_call.function.arguments

                                with tracer.start_as_current_span("tool.execute") as tool_span:
                                    tool_span.set_attribute("tool.name", function_name)
                                    add_trace_event("tool.arguments", {
                                        "args": arguments_str,
                                    })

                                    if function_name in self.tool_map:
                                        try:
                                            arguments = json.loads(arguments_str)
                                            tool_func = self.tool_map[function_name]
                                            result = tool_func(**arguments)
                                            if inspect.iscoroutine(result):
                                                result = await result

                                            add_trace_event("tool.result", {"result": str(result)})
                                            messages.append({
                                                "tool_call_id": tool_call.id,
                                                "role": "tool",
                                                "name": function_name,
                                                "content": str(result)
                                            })
                                        except Exception as e:
                                            record_error(tool_span, e)
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
                            continue

                        final_content = msg.content
                        break

                    except Exception as e:
                        record_error(llm_span, e)
                        error_str = str(e)
                        logger.error(f"LiteLLM error: {error_str}")

                        span.set_attribute("agent.turn_count", current_turn)
                        span.set_attribute("agent.total_input_tokens", total_input_tokens)
                        span.set_attribute("agent.total_output_tokens", total_output_tokens)

                        if "Connection error" in error_str or "Connection refused" in error_str or "Could not establish connection" in error_str:
                            friendly_msg = (
                                f"Error: Could not connect to the LLM provider at {self.api_base or 'default location'}. "
                                "Please ensure the service is running and accessible."
                            )
                            return AgentResponse(content=friendly_msg)

                        if "AuthenticationError" in error_str or "api_key client option must be set" in error_str:
                            friendly_msg = (
                                "Error: Authentication failed. If using Llama.cpp via OpenAI-compatible API, "
                                "ensure an API key is provided (even if dummy like 'sk-no-key-required')."
                            )
                            return AgentResponse(content=friendly_msg)

                        return AgentResponse(content=f"Error: {error_str}")

            span.set_attribute("agent.turn_count", current_turn)
            span.set_attribute("agent.total_input_tokens", total_input_tokens)
            span.set_attribute("agent.total_output_tokens", total_output_tokens)

            return AgentResponse(content=final_content or "")
