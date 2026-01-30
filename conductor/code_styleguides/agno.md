# Agno Best Practices

This guide outlines best practices for working with the Agno framework in the Sidestage project, based on official documentation and production patterns.

## 0. Development Workflow

### Use Agno MCP for Research
When investigating Agno capabilities, API references, or best practices, **always use the Agno MCP tool** (`SearchAgno`) first. Do not manually trawl through the `.venv` directory or internal library source code unless the MCP tool fails to provide sufficient information or specific implementation details are required that are not covered in the documentation.

### Search for Cookbooks
When implementing features or solving specific architectural problems, use the `SearchAgno` tool specifically to find **"cookbooks"** or official examples. Agno's internal patterns are best captured in these cookbooks; solutions should follow these official patterns and examples as closely as possible to ensure compatibility and maintainability.

## 1. Instruction & Prompt Engineering

### Use Modular Instructions
Instead of one giant string, use a list of strings for the `instructions` parameter. This makes it easier to add, remove, or toggle specific behaviors.
```python
instructions = [
    "Identify strictly as the Sidestage Co-Author.",
    "Maintain a creative and collaborative tone.",
    "Use provided tools to manage NPCs and locations."
]
```

### Enable Instruction Tags
Set `use_instruction_tags=True` in the `Agent` initialization. This wraps the system prompt in `<instructions>` tags, which improves the model's ability to follow guidance, especially for local models (LLama, Gemma).

### Use Dedent for Readability
When using multi-line strings for `description` or `system_message`, always use `textwrap.dedent` to avoid leading whitespace in the prompt.

## 2. Persona Enforcement

### Handle Stubborn Models (e.g., Gemma)
Some models have strong internal priors (e.g., identifying as "a model trained by Google"). To override this:
1.  **Forceful Instructions:** Add a specific identity section.
2.  **Few-Shotting:** Use the `additional_input` parameter to provide examples of correct self-identification.

```python
from agno.models.message import Message

Agent(
    additional_input=[
        Message(role="user", content="Who are you?"),
        Message(role="assistant", content="I am the Sidestage Co-Author...")
    ]
)
```

## 3. Production & Observability

### Enable Tracing
Always enable tracing in the `AgentOS` for production and debugging.
```python
agent_os = AgentOS(agents=[agent], tracing=True)
```
Traces can be viewed at `http://localhost:7777` (default).

### Persistent Storage
Always provide a `db` (e.g., `SqliteDb` or `PostgresDb`) to both the `Agent` and `AgentOS`. This ensures that:
- Traces are persisted.
- Sessions and memory are saved across restarts.

## 4. Context Management

### Time & Location Awareness
Enable `add_datetime_to_context=True` and `add_location_to_context=True` when relevant to ground the agent in reality.

### Markdown Support
Always set `markdown=True` to ensure the agent uses proper formatting for readability in UIs.
