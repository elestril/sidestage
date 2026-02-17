# Code Review: Section 05 - Mock Actor

The implementation is mostly faithful to the plan but has several issues ranging from a missing test to a misleading log message and a type-safety concern.

1. MISSING TEST: test_endpoints_return_404_when_mock_agent_not_set (MEDIUM)
The plan specifies a test `test_endpoints_return_404_when_mock_agent_not_set` in `tests/unit/test_mock_actor_routes.py`. This test is completely absent from the diff. The plan explains that when SIDESTAGE_MOCK_AGENT is not set, the routes are never registered, so requests naturally 404. While no explicit handler is needed, the test should still exist to verify this behavioral contract.

2. MISLEADING LOG OUTPUT IN server.py (LOW-MEDIUM)
At `server.py` line 95, the log message still prints `args.port` (the CLI default of 8000), but the actual port override via SIDESTAGE_PORT happens after the log. If SIDESTAGE_PORT=8001, the log says 'Starting on 0.0.0.0:8000' but the server actually binds to 8001.

3. TYPE ANNOTATION MISMATCH ON self.agent (LOW-MEDIUM)
At `actors.py` line 70, `self.agent` is typed as `LiteLLMAgent | None`. The mock injection assigns a `MockLLMAgent` instance, which is not a subclass of `LiteLLMAgent`. This is duck-typed and works at runtime, but will fail Pyright/mypy type checking.

4. UNUSED IMPORT in mock_actor.py (LOW)
`field` is imported from `dataclasses` but never used anywhere in the file.

5. SECURITY: NO INPUT VALIDATION ON MockAgentConfigureRequest (LOW)
`responses` is typed as `list[dict[str, Any]]`. Each dict is unpacked directly into `MockResponse(**r)`. If a malformed dict is sent, this will raise a TypeError at runtime. These routes are test-only and gated behind SIDESTAGE_MOCK_AGENT.

6. LIST pop(0) PERFORMANCE (TRIVIAL)
`self.responses.pop(0)` is O(n). For a test mock with a handful of responses this is irrelevant.
