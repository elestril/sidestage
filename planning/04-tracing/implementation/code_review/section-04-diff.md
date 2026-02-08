diff --git a/src/sidestage/agent.py b/src/sidestage/agent.py
index 382e1f3..84c305d 100644
--- a/src/sidestage/agent.py
+++ b/src/sidestage/agent.py
@@ -5,7 +5,11 @@ from typing import List, Callable, Optional, Dict, Any, Union
 from pydantic import BaseModel
 import litellm
 
+from opentelemetry import trace
+from sidestage.tracing.middleware import add_trace_event, record_error
+
 logger = logging.getLogger(__name__)
+tracer = trace.get_tracer("sidestage.agent")
 
 class AgentResponse(BaseModel):
     content: str
@@ -83,104 +87,143 @@ class LiteLLMAgent:
         }
 
     async def arun(self, message: str, context: str | None = None, stream: bool = False) -> AgentResponse:
-        messages = []
-        if self.instructions:
-            system_msg = "\n".join(self.instructions)
-            messages.append({"role": "system", "content": system_msg})
+        with tracer.start_as_current_span("agent.run") as span:
+            span.set_attribute("agent.name", self.name)
+            span.set_attribute("gen_ai.request.model", self.model)
 
-        if context:
-            messages.append({"role": "system", "content": context})
+            messages = []
+            if self.instructions:
+                system_msg = "\n".join(self.instructions)
+                messages.append({"role": "system", "content": system_msg})
 
-        messages.append({"role": "user", "content": message})
-        
-        # Maximum turns to prevent infinite loops
-        max_turns = 5
-        current_turn = 0
-        
-        final_content = ""
-        
-        while current_turn < max_turns:
-            current_turn += 1
-            
-            try:
-                response = await litellm.acompletion(
-                    model=self.model,
-                    api_base=self.api_base,
-                    api_key=self.api_key,
-                    messages=messages,
-                    tools=self.tool_schemas if self.tool_schemas else None,
-                    tool_choice="auto" if self.tool_schemas else None,
-                    stream=False # We handle streaming internally if needed, but for now blocking
-                )
-                
-                from typing import cast, Any
-                resp_obj = cast(Any, response)
-                msg = resp_obj.choices[0].message
-                messages.append(msg)
-                
-                if msg.tool_calls:
-                    logger.info(f"Agent requested tool calls: {len(msg.tool_calls)}")
-                    for tool_call in msg.tool_calls:
-                        function_name = tool_call.function.name
-                        arguments_str = tool_call.function.arguments
-                        
-                        if function_name in self.tool_map:
-                            try:
-                                arguments = json.loads(arguments_str)
-                                tool_func = self.tool_map[function_name]
-                                result = tool_func(**arguments)
-                                if inspect.iscoroutine(result):
-                                    result = await result
-                                
-                                messages.append({
-                                    "tool_call_id": tool_call.id,
-                                    "role": "tool",
-                                    "name": function_name,
-                                    "content": str(result)
-                                })
-                            except Exception as e:
-                                error_msg = f"Error executing {function_name}: {e}"
-                                logger.error(error_msg)
-                                messages.append({
-                                    "tool_call_id": tool_call.id,
-                                    "role": "tool",
-                                    "name": function_name,
-                                    "content": error_msg
-                                })
-                        else:
-                            messages.append({
-                                "tool_call_id": tool_call.id,
-                                "role": "tool",
-                                "name": function_name,
-                                "content": f"Error: Tool {function_name} not found"
-                            })
-                    # Loop back to get response after tool output
-                    continue
-                
-                # No tool calls, this is the final response
-                final_content = msg.content
-                break
-                
-            except Exception as e:
-                error_str = str(e)
-                logger.error(f"LiteLLM error: {error_str}")
-                
-                # Check for common connection errors
-                if "Connection error" in error_str or "Connection refused" in error_str:
-                    friendly_msg = (
-                        f"Error: Could not connect to the LLM provider at {self.api_base or 'default location'}. "
-                        "Please ensure the service is running and accessible."
-                    )
-                    return AgentResponse(content=friendly_msg)
-                
-                # Check for authentication errors
-                if "AuthenticationError" in error_str or "api_key client option must be set" in error_str:
-                     friendly_msg = (
-                        "Error: Authentication failed. If using Llama.cpp via OpenAI-compatible API, "
-                        "ensure an API key is provided (even if dummy like 'sk-no-key-required')."
-                    )
-                     return AgentResponse(content=friendly_msg)
-
-                return AgentResponse(content=f"Error: {error_str}")
-        
-        return AgentResponse(content=final_content or "")
+            if context:
+                messages.append({"role": "system", "content": context})
+
+            messages.append({"role": "user", "content": message})
+
+            max_turns = 5
+            current_turn = 0
+            total_input_tokens = 0
+            total_output_tokens = 0
+            final_content = ""
+
+            while current_turn < max_turns:
+                current_turn += 1
+
+                with tracer.start_as_current_span("llm.completion") as llm_span:
+                    llm_span.set_attribute("agent.turn", current_turn)
+
+                    add_trace_event("gen_ai.prompt", {
+                        "role": "user",
+                        "content": message,
+                    })
+
+                    try:
+                        response = await litellm.acompletion(
+                            model=self.model,
+                            api_base=self.api_base,
+                            api_key=self.api_key,
+                            messages=messages,
+                            tools=self.tool_schemas if self.tool_schemas else None,
+                            tool_choice="auto" if self.tool_schemas else None,
+                            stream=False,
+                        )
+
+                        from typing import cast
+                        resp_obj = cast(Any, response)
+                        msg = resp_obj.choices[0].message
+
+                        add_trace_event("gen_ai.completion", {
+                            "content": msg.content or "",
+                        })
+
+                        # Extract token usage
+                        usage = getattr(resp_obj, 'usage', None)
+                        if usage:
+                            input_tokens = getattr(usage, 'prompt_tokens', 0) or 0
+                            output_tokens = getattr(usage, 'completion_tokens', 0) or 0
+                            llm_span.set_attribute("gen_ai.usage.input_tokens", input_tokens)
+                            llm_span.set_attribute("gen_ai.usage.output_tokens", output_tokens)
+                            total_input_tokens += input_tokens
+                            total_output_tokens += output_tokens
+
+                        llm_span.set_attribute("gen_ai.response.finish_reasons",
+                            [choice.finish_reason for choice in resp_obj.choices])
+
+                        messages.append(msg)
+
+                        if msg.tool_calls:
+                            logger.info(f"Agent requested tool calls: {len(msg.tool_calls)}")
+                            for tool_call in msg.tool_calls:
+                                function_name = tool_call.function.name
+                                arguments_str = tool_call.function.arguments
+
+                                with tracer.start_as_current_span("tool.execute") as tool_span:
+                                    tool_span.set_attribute("tool.name", function_name)
+                                    add_trace_event("tool.arguments", {
+                                        "args": arguments_str,
+                                    })
+
+                                    if function_name in self.tool_map:
+                                        try:
+                                            arguments = json.loads(arguments_str)
+                                            tool_func = self.tool_map[function_name]
+                                            result = tool_func(**arguments)
+                                            if inspect.iscoroutine(result):
+                                                result = await result
+
+                                            add_trace_event("tool.result", {"result": str(result)})
+                                            messages.append({
+                                                "tool_call_id": tool_call.id,
+                                                "role": "tool",
+                                                "name": function_name,
+                                                "content": str(result)
+                                            })
+                                        except Exception as e:
+                                            record_error(tool_span, e)
+                                            error_msg = f"Error executing {function_name}: {e}"
+                                            logger.error(error_msg)
+                                            messages.append({
+                                                "tool_call_id": tool_call.id,
+                                                "role": "tool",
+                                                "name": function_name,
+                                                "content": error_msg
+                                            })
+                                    else:
+                                        messages.append({
+                                            "tool_call_id": tool_call.id,
+                                            "role": "tool",
+                                            "name": function_name,
+                                            "content": f"Error: Tool {function_name} not found"
+                                        })
+                            continue
+
+                        final_content = msg.content
+                        break
+
+                    except Exception as e:
+                        record_error(llm_span, e)
+                        error_str = str(e)
+                        logger.error(f"LiteLLM error: {error_str}")
+
+                        if "Connection error" in error_str or "Connection refused" in error_str:
+                            friendly_msg = (
+                                f"Error: Could not connect to the LLM provider at {self.api_base or 'default location'}. "
+                                "Please ensure the service is running and accessible."
+                            )
+                            return AgentResponse(content=friendly_msg)
+
+                        if "AuthenticationError" in error_str or "api_key client option must be set" in error_str:
+                            friendly_msg = (
+                                "Error: Authentication failed. If using Llama.cpp via OpenAI-compatible API, "
+                                "ensure an API key is provided (even if dummy like 'sk-no-key-required')."
+                            )
+                            return AgentResponse(content=friendly_msg)
+
+                        return AgentResponse(content=f"Error: {error_str}")
+
+            span.set_attribute("agent.turn_count", current_turn)
+            span.set_attribute("agent.total_input_tokens", total_input_tokens)
+            span.set_attribute("agent.total_output_tokens", total_output_tokens)
+
+            return AgentResponse(content=final_content or "")
diff --git a/src/sidestage/campaign.py b/src/sidestage/campaign.py
index ed78147..6281d74 100644
--- a/src/sidestage/campaign.py
+++ b/src/sidestage/campaign.py
@@ -4,6 +4,8 @@ import httpx
 from pathlib import Path
 from typing import Optional, List, Dict, Any, Tuple, AsyncGenerator
 
+from opentelemetry import trace
+
 from sidestage.agent import LiteLLMAgent
 from sidestage.storage import Storage
 from sidestage.tools import WorldTools
@@ -21,6 +23,7 @@ from sidestage.config import LLMConfig, SidestageConfig
 from sidestage import config
 
 logger = logging.getLogger(__name__)
+tracer = trace.get_tracer("sidestage.campaign")
 
 class Campaign:
     """
@@ -157,37 +160,45 @@ class Campaign:
         Uses the migration parser to read all entity types (characters, scenes,
         locations, items, events) and upserts them into the database.
         """
-        logger.info("Reloading default content from data directory...")
+        with tracer.start_as_current_span("campaign.reload_defaults") as span:
+            span.set_attribute("sidestage.scene.id", "campaign_planning")
 
-        project_root = Path(__file__).parent.parent.parent
-        defaults_dir = project_root / "data" / "campaign_defaults" / "markdown"
+            logger.info("Reloading default content from data directory...")
 
-        if not defaults_dir.exists():
-            logger.warning(f"Defaults directory not found at {defaults_dir}. Skipping.")
-            return
+            project_root = Path(__file__).parent.parent.parent
+            defaults_dir = project_root / "data" / "campaign_defaults" / "markdown"
 
-        result = parse_directory(defaults_dir)
+            if not defaults_dir.exists():
+                logger.warning(f"Defaults directory not found at {defaults_dir}. Skipping.")
+                span.set_attribute("entities.loaded_count", 0)
+                return
 
-        for issue in result.errors:
-            logger.error(f"Error loading default: {issue.message} ({issue.file_path})")
-        for issue in result.warnings:
-            logger.warning(f"Warning loading default: {issue.message} ({issue.file_path})")
+            result = parse_directory(defaults_dir)
 
-        for entity in result.entities:
-            try:
-                if isinstance(entity, Character):
-                    self.storage.add_character(entity)
-                elif isinstance(entity, Location):
-                    self.storage.add_location(entity)
-                elif isinstance(entity, Item):
-                    self.storage.add_item(entity)
-                elif isinstance(entity, Scene):
-                    self.storage.add_scene(entity)
-                elif isinstance(entity, Event):
-                    self.storage.add_event(entity)
-                logger.info(f"Loaded default {type(entity).__name__}: {entity.name} ({entity.id})")
-            except Exception as e:
-                logger.error(f"Error loading default entity {entity.id}: {e}")
+            for issue in result.errors:
+                logger.error(f"Error loading default: {issue.message} ({issue.file_path})")
+            for issue in result.warnings:
+                logger.warning(f"Warning loading default: {issue.message} ({issue.file_path})")
+
+            count = 0
+            for entity in result.entities:
+                try:
+                    if isinstance(entity, Character):
+                        self.storage.add_character(entity)
+                    elif isinstance(entity, Location):
+                        self.storage.add_location(entity)
+                    elif isinstance(entity, Item):
+                        self.storage.add_item(entity)
+                    elif isinstance(entity, Scene):
+                        self.storage.add_scene(entity)
+                    elif isinstance(entity, Event):
+                        self.storage.add_event(entity)
+                    count += 1
+                    logger.info(f"Loaded default {type(entity).__name__}: {entity.name} ({entity.id})")
+                except Exception as e:
+                    logger.error(f"Error loading default entity {entity.id}: {e}")
+
+            span.set_attribute("entities.loaded_count", count)
 
     def _ensure_llm_availability(self) -> None:
         """
diff --git a/src/sidestage/character.py b/src/sidestage/character.py
index 21ee6c9..291046a 100644
--- a/src/sidestage/character.py
+++ b/src/sidestage/character.py
@@ -3,8 +3,11 @@ import asyncio
 from typing import Optional, List, Dict, Any, TYPE_CHECKING
 from pathlib import Path
 
+from opentelemetry import trace
+
 from sidestage.schemas import Character, Event, ChatMessage
 from sidestage.agent import LiteLLMAgent
+from sidestage.tracing.middleware import record_error
 
 if TYPE_CHECKING:
     from sidestage.graph.client import GraphClient
@@ -12,6 +15,7 @@ if TYPE_CHECKING:
     from sidestage.health import CampaignHealth
 
 logger = logging.getLogger(__name__)
+tracer = trace.get_tracer("sidestage.character")
 
 class AgentActor:
     """
@@ -111,37 +115,44 @@ class AgentActor:
         if not isinstance(event, ChatMessage):
             return
 
-        logger.info(f"AgentActor ({self.character.name}) reacting to message from {event.actor_id}")
-
-        if not self.agent:
-            return
-
-        context_text = None
-        if self.graph_client is not None and self.scene_id is not None:
+        with tracer.start_as_current_span("agent.on_event") as span:
+            span.set_attribute("sidestage.character.id", self.character.id)
+            span.set_attribute("sidestage.character.name", self.character.name)
             try:
-                from sidestage.memory.context import assemble_context
-                result = await assemble_context(
-                    client=self.graph_client,
-                    owner_id=self.character.id,
-                    scene_id=self.scene_id,
-                    present_character_ids=self.present_character_ids or [],
-                    recent_messages=self.scene_logic.messages,
-                    context_limit=self.context_limit,
-                )
-                parts = [p for p in (result.memory_text, result.chat_text) if p]
-                context_text = "\n\n".join(parts) or None
-            except Exception:
-                logger.exception("Failed to assemble context for %s", self.character.name)
-
-        response = await self.agent.arun(event.message, context=context_text)
-
-        if response.content:
-            reply = self.scene_logic.create_message(
-                actor_id=self.actor_id,
-                text=response.content,
-                character_id=self.character.id
-            )
-            await self.scene_logic.queue.put(reply)
+                logger.info(f"AgentActor ({self.character.name}) reacting to message from {event.actor_id}")
+
+                if not self.agent:
+                    return
+
+                context_text = None
+                if self.graph_client is not None and self.scene_id is not None:
+                    try:
+                        from sidestage.memory.context import assemble_context
+                        result = await assemble_context(
+                            client=self.graph_client,
+                            owner_id=self.character.id,
+                            scene_id=self.scene_id,
+                            present_character_ids=self.present_character_ids or [],
+                            recent_messages=self.scene_logic.messages,
+                            context_limit=self.context_limit,
+                        )
+                        parts = [p for p in (result.memory_text, result.chat_text) if p]
+                        context_text = "\n\n".join(parts) or None
+                    except Exception:
+                        logger.exception("Failed to assemble context for %s", self.character.name)
+
+                response = await self.agent.arun(event.message, context=context_text)
+
+                if response.content:
+                    reply = self.scene_logic.create_message(
+                        actor_id=self.actor_id,
+                        text=response.content,
+                        character_id=self.character.id
+                    )
+                    await self.scene_logic.queue.put(reply)
+            except Exception as exc:
+                record_error(span, exc)
+                logger.exception("Error in on_event for %s", self.character.name)
 
 class CharacterLogic:
     """
diff --git a/src/sidestage/memory/context.py b/src/sidestage/memory/context.py
index 712f9da..a30ea3a 100644
--- a/src/sidestage/memory/context.py
+++ b/src/sidestage/memory/context.py
@@ -9,6 +9,8 @@ from __future__ import annotations
 import logging
 from typing import TYPE_CHECKING
 
+from opentelemetry import trace
+
 from sidestage.memory.models import ContextResult, ContextMemories
 from sidestage.memory.store import get_memories_for_context, touch_memory
 
@@ -18,6 +20,7 @@ if TYPE_CHECKING:
     from sidestage.graph.client import GraphClient
 
 logger = logging.getLogger(__name__)
+tracer = trace.get_tracer("sidestage.memory.context")
 
 AVG_TOKENS_PER_WORD = 1.3
 DEFAULT_CHAT_HISTORY_RATIO = 0.20
@@ -98,41 +101,47 @@ async def assemble_context(
     Fetches all applicable memories, formats them, trims chat history,
     and returns a ContextResult ready for injection into the LLM prompt.
     """
-    # 1. Fetch memories
-    memories = await get_memories_for_context(
-        client, owner_id, scene_id, present_character_ids,
-    )
-
-    # 2. Touch accessed memories (non-blocking, best-effort)
-    memory_ids = []
-    if memories.common_scene_memory:
-        memory_ids.append(memories.common_scene_memory.id)
-    if memories.private_scene_memory:
-        memory_ids.append(memories.private_scene_memory.id)
-    for mem in memories.character_memories.values():
-        memory_ids.append(mem.id)
-    for mem in memories.world_facts:
-        memory_ids.append(mem.id)
-
-    for mid in memory_ids:
-        try:
-            await touch_memory(client, mid)
-        except Exception:
-            logger.warning("Failed to touch memory %s", mid)
-
-    # 3. Format memories
-    memory_text = _format_memories(memories, character_names=character_names)
-
-    # 4. Trim chat history
-    word_budget = int(context_limit * chat_history_ratio / AVG_TOKENS_PER_WORD)
-    chat_text = _trim_chat_history(recent_messages, word_budget)
-
-    # 5. Estimate tokens
-    total_text = memory_text + chat_text
-    token_estimate = _estimate_tokens(total_text)
-
-    return ContextResult(
-        memory_text=memory_text,
-        chat_text=chat_text,
-        token_estimate=token_estimate,
-    )
+    with tracer.start_as_current_span("memory.assemble_context") as span:
+        span.set_attribute("sidestage.owner_id", owner_id)
+        span.set_attribute("sidestage.scene.id", scene_id)
+
+        # 1. Fetch memories
+        memories = await get_memories_for_context(
+            client, owner_id, scene_id, present_character_ids,
+        )
+
+        # 2. Touch accessed memories (non-blocking, best-effort)
+        memory_ids = []
+        if memories.common_scene_memory:
+            memory_ids.append(memories.common_scene_memory.id)
+        if memories.private_scene_memory:
+            memory_ids.append(memories.private_scene_memory.id)
+        for mem in memories.character_memories.values():
+            memory_ids.append(mem.id)
+        for mem in memories.world_facts:
+            memory_ids.append(mem.id)
+
+        for mid in memory_ids:
+            try:
+                await touch_memory(client, mid)
+            except Exception:
+                logger.warning("Failed to touch memory %s", mid)
+
+        # 3. Format memories
+        memory_text = _format_memories(memories, character_names=character_names)
+
+        # 4. Trim chat history
+        word_budget = int(context_limit * chat_history_ratio / AVG_TOKENS_PER_WORD)
+        chat_text = _trim_chat_history(recent_messages, word_budget)
+
+        # 5. Estimate tokens
+        total_text = memory_text + chat_text
+        token_estimate = _estimate_tokens(total_text)
+
+        span.set_attribute("memory.token_estimate", token_estimate)
+
+        return ContextResult(
+            memory_text=memory_text,
+            chat_text=chat_text,
+            token_estimate=token_estimate,
+        )
diff --git a/src/sidestage/memory/tools.py b/src/sidestage/memory/tools.py
index ecf5056..76f4b20 100644
--- a/src/sidestage/memory/tools.py
+++ b/src/sidestage/memory/tools.py
@@ -7,6 +7,8 @@ import json
 import logging
 from typing import TYPE_CHECKING
 
+from opentelemetry import trace, context
+
 from sidestage.memory.store import (
     upsert_scene_memory,
     upsert_common_scene_memory,
@@ -14,6 +16,7 @@ from sidestage.memory.store import (
     upsert_world_fact,
 )
 from sidestage.memory.embeddings import embed_and_update
+from sidestage.tracing.middleware import add_trace_event, record_error
 
 if TYPE_CHECKING:
     from sidestage.config import LLMConfig
@@ -21,6 +24,7 @@ if TYPE_CHECKING:
     from sidestage.health import CampaignHealth
 
 logger = logging.getLogger(__name__)
+tracer = trace.get_tracer("sidestage.memory.tools")
 
 
 class MemoryTools:
@@ -45,12 +49,25 @@ class MemoryTools:
         self.scene_id = scene_id
 
     def _fire_embed(self, memory_id: str, content: str) -> None:
-        """Fire background embedding task if embed_config is available."""
+        """Fire background embedding task with trace context propagation."""
         if self.embed_config is not None:
+            ctx = context.get_current()
+
+            async def _embed_with_context():
+                token = context.attach(ctx)
+                try:
+                    with tracer.start_as_current_span("memory.embed") as span:
+                        span.set_attribute("memory.id", memory_id)
+                        await embed_and_update(
+                            self.client, self.embed_config, memory_id, content, self.health
+                        )
+                except Exception as exc:
+                    logger.debug("Background embed tracing error: %s", exc)
+                finally:
+                    context.detach(token)
+
             try:
-                asyncio.create_task(
-                    embed_and_update(self.client, self.embed_config, memory_id, content, self.health)
-                )
+                asyncio.create_task(_embed_with_context())
             except RuntimeError:
                 logger.debug("No event loop for background embed task")
 
@@ -68,15 +85,20 @@ class MemoryTools:
         Returns:
             JSON confirmation with memory ID.
         """
-        try:
-            memory = await upsert_scene_memory(
-                self.client, self.owner_id, self.scene_id, content, gametime=gametime,
-            )
-            self._fire_embed(memory.id, content)
-            return json.dumps({"status": "ok", "memory_id": memory.id})
-        except Exception as exc:
-            logger.warning("update_scene_memory failed: %s", exc)
-            return json.dumps({"status": "error", "message": str(exc)})
+        with tracer.start_as_current_span("memory.update_scene_memory") as span:
+            span.set_attribute("sidestage.owner_id", self.owner_id)
+            span.set_attribute("sidestage.scene.id", self.scene_id)
+            add_trace_event("memory.content", {"content": content})
+            try:
+                memory = await upsert_scene_memory(
+                    self.client, self.owner_id, self.scene_id, content, gametime=gametime,
+                )
+                self._fire_embed(memory.id, content)
+                return json.dumps({"status": "ok", "memory_id": memory.id})
+            except Exception as exc:
+                record_error(span, exc)
+                logger.warning("update_scene_memory failed: %s", exc)
+                return json.dumps({"status": "error", "message": str(exc)})
 
     async def update_character_memory(self, about_character_id: str, content: str, gametime: int | None = None) -> str:
         """Update your memory about another character.
@@ -91,15 +113,20 @@ class MemoryTools:
         Returns:
             JSON confirmation with memory ID.
         """
-        try:
-            memory = await upsert_character_memory(
-                self.client, self.owner_id, about_character_id, content, gametime=gametime,
-            )
-            self._fire_embed(memory.id, content)
-            return json.dumps({"status": "ok", "memory_id": memory.id})
-        except Exception as exc:
-            logger.warning("update_character_memory failed: %s", exc)
-            return json.dumps({"status": "error", "message": str(exc)})
+        with tracer.start_as_current_span("memory.update_character_memory") as span:
+            span.set_attribute("sidestage.owner_id", self.owner_id)
+            span.set_attribute("sidestage.character.about_id", about_character_id)
+            add_trace_event("memory.content", {"content": content})
+            try:
+                memory = await upsert_character_memory(
+                    self.client, self.owner_id, about_character_id, content, gametime=gametime,
+                )
+                self._fire_embed(memory.id, content)
+                return json.dumps({"status": "ok", "memory_id": memory.id})
+            except Exception as exc:
+                record_error(span, exc)
+                logger.warning("update_character_memory failed: %s", exc)
+                return json.dumps({"status": "error", "message": str(exc)})
 
 
 class DmMemoryTools:
@@ -122,12 +149,25 @@ class DmMemoryTools:
         self.dm_actor_id = dm_actor_id
 
     def _fire_embed(self, memory_id: str, content: str) -> None:
-        """Fire background embedding task if embed_config is available."""
+        """Fire background embedding task with trace context propagation."""
         if self.embed_config is not None:
+            ctx = context.get_current()
+
+            async def _embed_with_context():
+                token = context.attach(ctx)
+                try:
+                    with tracer.start_as_current_span("memory.embed") as span:
+                        span.set_attribute("memory.id", memory_id)
+                        await embed_and_update(
+                            self.client, self.embed_config, memory_id, content, self.health
+                        )
+                except Exception as exc:
+                    logger.debug("Background embed tracing error: %s", exc)
+                finally:
+                    context.detach(token)
+
             try:
-                asyncio.create_task(
-                    embed_and_update(self.client, self.embed_config, memory_id, content, self.health)
-                )
+                asyncio.create_task(_embed_with_context())
             except RuntimeError:
                 logger.debug("No event loop for background embed task")
 
@@ -144,15 +184,20 @@ class DmMemoryTools:
         Returns:
             JSON confirmation with memory ID.
         """
-        try:
-            memory = await upsert_common_scene_memory(
-                self.client, scene_id, content, gametime=gametime,
-            )
-            self._fire_embed(memory.id, content)
-            return json.dumps({"status": "ok", "memory_id": memory.id})
-        except Exception as exc:
-            logger.warning("update_common_memory failed: %s", exc)
-            return json.dumps({"status": "error", "message": str(exc)})
+        with tracer.start_as_current_span("memory.update_common_memory") as span:
+            span.set_attribute("sidestage.dm_actor_id", self.dm_actor_id)
+            span.set_attribute("sidestage.scene.id", scene_id)
+            add_trace_event("memory.content", {"content": content})
+            try:
+                memory = await upsert_common_scene_memory(
+                    self.client, scene_id, content, gametime=gametime,
+                )
+                self._fire_embed(memory.id, content)
+                return json.dumps({"status": "ok", "memory_id": memory.id})
+            except Exception as exc:
+                record_error(span, exc)
+                logger.warning("update_common_memory failed: %s", exc)
+                return json.dumps({"status": "error", "message": str(exc)})
 
     async def update_canonical_memory(self, scene_id: str, content: str, gametime: int | None = None) -> str:
         """Update the canonical (DM truth) scene memory.
@@ -167,15 +212,20 @@ class DmMemoryTools:
         Returns:
             JSON confirmation with memory ID.
         """
-        try:
-            memory = await upsert_scene_memory(
-                self.client, self.dm_actor_id, scene_id, content, gametime=gametime,
-            )
-            self._fire_embed(memory.id, content)
-            return json.dumps({"status": "ok", "memory_id": memory.id})
-        except Exception as exc:
-            logger.warning("update_canonical_memory failed: %s", exc)
-            return json.dumps({"status": "error", "message": str(exc)})
+        with tracer.start_as_current_span("memory.update_canonical_memory") as span:
+            span.set_attribute("sidestage.dm_actor_id", self.dm_actor_id)
+            span.set_attribute("sidestage.scene.id", scene_id)
+            add_trace_event("memory.content", {"content": content})
+            try:
+                memory = await upsert_scene_memory(
+                    self.client, self.dm_actor_id, scene_id, content, gametime=gametime,
+                )
+                self._fire_embed(memory.id, content)
+                return json.dumps({"status": "ok", "memory_id": memory.id})
+            except Exception as exc:
+                record_error(span, exc)
+                logger.warning("update_canonical_memory failed: %s", exc)
+                return json.dumps({"status": "error", "message": str(exc)})
 
     async def add_world_fact(self, about_entity_id: str, content: str, visibility: str = "common") -> str:
         """Add or update a world fact about an entity.
@@ -192,12 +242,16 @@ class DmMemoryTools:
         Returns:
             JSON confirmation with memory ID.
         """
-        try:
-            memory = await upsert_world_fact(
-                self.client, about_entity_id, content, visibility=visibility, owner_id=None,
-            )
-            self._fire_embed(memory.id, content)
-            return json.dumps({"status": "ok", "memory_id": memory.id})
-        except Exception as exc:
-            logger.warning("add_world_fact failed: %s", exc)
-            return json.dumps({"status": "error", "message": str(exc)})
+        with tracer.start_as_current_span("memory.add_world_fact") as span:
+            span.set_attribute("sidestage.entity_id", about_entity_id)
+            add_trace_event("memory.content", {"content": content})
+            try:
+                memory = await upsert_world_fact(
+                    self.client, about_entity_id, content, visibility=visibility, owner_id=None,
+                )
+                self._fire_embed(memory.id, content)
+                return json.dumps({"status": "ok", "memory_id": memory.id})
+            except Exception as exc:
+                record_error(span, exc)
+                logger.warning("add_world_fact failed: %s", exc)
+                return json.dumps({"status": "error", "message": str(exc)})
diff --git a/src/sidestage/scene.py b/src/sidestage/scene.py
index d033b43..7c4333a 100644
--- a/src/sidestage/scene.py
+++ b/src/sidestage/scene.py
@@ -3,12 +3,15 @@ from typing import AsyncGenerator, Optional, Dict, Any, List, Callable, Awaitabl
 from datetime import datetime
 import uuid
 
+from opentelemetry import trace
+
 from sidestage.schemas import Character, Scene, ChatRequest, ChatMessage, Event
 from sidestage.entities import entity_to_markdown
 from sidestage.bus import EventQueue
 from sidestage.character import CharacterLogic
 from sidestage.storage import Storage
 from sidestage.agent import LiteLLMAgent
+from sidestage.tracing.middleware import record_error
 
 from typing import TYPE_CHECKING
 if TYPE_CHECKING:
@@ -17,6 +20,7 @@ if TYPE_CHECKING:
     from sidestage.health import CampaignHealth
 
 logger = logging.getLogger(__name__)
+tracer = trace.get_tracer("sidestage.scene")
 
 # Callback type for broadcasting events to websocket clients
 BroadcastFn = Callable[[ChatMessage], Awaitable[None]]
@@ -67,38 +71,49 @@ class SceneLogic:
         if not isinstance(event, ChatMessage):
             return
 
-        # (a) Persist
-        self.data.messages.append(event)
-        self.storage.update_scene(self.data)
-
-        if self.graph_client is not None:
-            from sidestage.graph import create_entity, link
+        with tracer.start_as_current_span("scene.process_event") as span:
+            span.set_attribute("sidestage.scene.id", self.id)
+            span.set_attribute("sidestage.event.id", event.id)
+            span.set_attribute("sidestage.event.type", type(event).__name__)
+            span.set_attribute("sidestage.actor.id", event.actor_id or "unknown")
             try:
-                await create_entity(self.graph_client, event)
-                await link(self.graph_client, self.data.id, "HAS_EVENT", event.id)
-                if event.character_id:
-                    await link(self.graph_client, event.id, "INVOLVES", event.character_id)
-            except Exception:
-                logger.exception("Failed to persist event %s to graph", event.id)
-
-        # (b) Broadcast to websockets
-        if self._broadcast_fn:
-            await self._broadcast_fn(event)
-
-        # (c) For user-originated events: send to all NPCs
-        if event.actor_id == "user":
-            await self._dispatch_to_npcs(event)
+                # (a) Persist
+                self.data.messages.append(event)
+                self.storage.update_scene(self.data)
+
+                if self.graph_client is not None:
+                    from sidestage.graph import create_entity, link
+                    try:
+                        await create_entity(self.graph_client, event)
+                        await link(self.graph_client, self.data.id, "HAS_EVENT", event.id)
+                        if event.character_id:
+                            await link(self.graph_client, event.id, "INVOLVES", event.character_id)
+                    except Exception:
+                        logger.exception("Failed to persist event %s to graph", event.id)
+
+                # (b) Broadcast to websockets
+                if self._broadcast_fn:
+                    await self._broadcast_fn(event)
+
+                # (c) For user-originated events: send to all NPCs
+                if event.actor_id == "user":
+                    await self._dispatch_to_npcs(event)
+            except Exception as exc:
+                record_error(span, exc)
+                raise
 
     async def _dispatch_to_npcs(self, event: ChatMessage) -> None:
         """Send an event to all active NPC agents."""
-        for char_logic in self.characters.values():
-            if char_logic.actor is not None:
-                try:
-                    await char_logic.actor.on_event(event)
-                except Exception:
-                    logger.exception(
-                        "Error dispatching to NPC %s", char_logic.data.name
-                    )
+        with tracer.start_as_current_span("scene.dispatch_to_npcs") as span:
+            span.set_attribute("sidestage.npc_count", len(self.characters))
+            for char_logic in self.characters.values():
+                if char_logic.actor is not None:
+                    try:
+                        await char_logic.actor.on_event(event)
+                    except Exception:
+                        logger.exception(
+                            "Error dispatching to NPC %s", char_logic.data.name
+                        )
 
     async def activate(self) -> None:
         """
