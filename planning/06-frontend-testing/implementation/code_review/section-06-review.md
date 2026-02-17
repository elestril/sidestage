# Code Review: Section 06 - E2E Test Scenarios

## Critical
1. `TestRealTimeSyncEntities._setup` doesn't set `self._base` — runtime crash bug
2. `_activate_scene` duplicated across 3 files — should be in conftest

## Important
3. Missing `test_error_event_rendering` — can't work because MockLLMAgent doesn't plumb event_type
4. Missing `test_entity_created_via_api_appears_in_both_clients`
5. Mock agent reset not consistent — should use fixture teardown
6. Weak URL assertion in `test_default_scene_is_campaign_planning`

## Minor (let go)
7. `time.sleep` in `_activate_scene` — pragmatic for E2E
8. init message pollutes history — tests use specific predicates
9. `wait_for_timeout` in campaign operations — works reliably
10. Brittle CSS locator in LLM test — placeholder test
11. LogObserver not used in LLM test — placeholder test
12. Content equality not byte-for-byte in sync test — overkill
13. `test_scene_switch_reloads_messages` doesn't verify message clearing — frontend doesn't clear them
