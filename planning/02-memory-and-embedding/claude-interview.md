# Interview Transcript: Memory and Embedding System

## Q1: Embedding Model Strategy
**Question:** For the initial implementation, should we support only local embeddings (sentence-transformers/all-MiniLM-L6-v2), or also cloud embeddings (Google Vertex AI)?

**Answer:** Use the configured "embed" LLM from the campaign config. This means embedding models are configured through the existing `llms` config section, not as a separate system.

## Q2: Memory Creation Timing
**Question:** When should memories be created? Every chat message/event becomes a memory immediately, or batch/summarize at scene boundaries?

**Answer:** Both (configurable). Real-time for important events, batch summarization as a separate pass.

## Q3: Expected Scale
**Question:** What scale of memories do you expect per campaign?

**Answer:** Large (tens of thousands). 10k+ memories per campaign.

## Q4: Embedding API
**Question:** Should we use LiteLLM's embedding API (litellm.aembedding()) which supports OpenAI-compatible endpoints including local llama.cpp /v1/embeddings?

**Answer:** Yes, use LiteLLM embedding API. Consistent with existing architecture — same provider abstraction as chat models.

## Q5: Token Budget for Memory Context
**Question:** What's the target token budget for memory sections in agent prompts?

**Answer:** Make that a config option of the "llm" config section. The configured default endpoint has a 16k limit. At config load time: verify that the configured context limit is supported via the /status endpoint.

## Q6: Memory-Entity Storage
**Question:** Should memories have relationships to entities in the graph, or store entity references as properties?

**Answer:** Graph relationships. Memory nodes connected via typed edges, enabling traversal queries like "all memories involving Character X at Location Y."

## Q7: Memory Types
**Question:** What memory types should we implement for this split?

**Answer:** All four types — event memories, fact memories, relationship memories, and interaction memories.

## Q8: Error Handling on Embedding Failure
**Question:** When embedding generation fails, what should happen?

**Answer:** The campaign should enter an unhealthy state, during which it tries to flush outstanding work but does not accept chat input. No silent failures.

## Q9: Memory Expiration
**Question:** Should old memories expire automatically?

**Answer:** No auto-expiration. Keep all memories indefinitely. But make sure an access decay counter is available — there will be a cleanup job in the future that will use it.

## Q10: Fact Extraction Method
**Question:** How should facts be extracted from events?

**Answer:** Simple heuristic extraction. Pattern-based extraction (regex, keywords) without LLM calls. Fast but sufficient for initial implementation.

## Q11: Campaign Health Status
**Question:** Does the campaign already have a health mechanism, or is this new?

**Answer:** New health status concept. Add a health enum (healthy/degraded/unhealthy) to Campaign with WebSocket notifications to the frontend.
