Implement tracing support

* Every event that arrives at a Scene should trigger a new trace. 
* Traces must contain every llm call, memory read/write, and any other tool call
* They must contain the full llm prompt and parameters of every agent invoked
* Traces must support nested spans, i.e. if they trigger multiple 
nested LLM calls for instance for embedding, or because a DM agent is invoked to review actions
* Tracing can be turned on and off in the UI, there is a default in the config.yml
* There must be a trace viewer on the UI, that allows per-scene trace viewing

Strongly consider opentelemetry for the instrumentation.
