# Code Review: Section 01 - TraceConfig Model and Configuration

The implementation faithfully matches the section plan. The TraceConfig model, its integration into SidestageConfig, and the test file all align with the specification. That said, there are several issues worth raising:

1. WEAK EXCEPTION ASSERTIONS (tests/unit/test_trace_config.py, lines 79-100): Every validation test uses `pytest.raises(Exception)` -- the broadest possible exception type. This is a lazy test. If the code raises an unexpected exception (TypeError, AttributeError, import error), the test still passes. These should use `pytest.raises(pydantic.ValidationError)` to assert the specific Pydantic validation error. Otherwise these tests are not actually proving that the `ge=1` constraint is what rejects the value.

2. ROUNDTRIP TEST FIGHTS THE AUTOUSE FIXTURE (tests/unit/test_trace_config.py, line 146): The `test_config_yml_roundtrip` method calls `sidestage_config.init(tmp_path)` directly, but the `_init_config` autouse fixture in `tests/conftest.py` has already called `sidestage_config.init(tmp_path)` with a DIFFERENT `tmp_path` before the test runs. This means the test writes its own config.yml, then calls init() which mutates the global `_instance` singleton, and then the fixture teardown sets `_instance = None`. The test happens to work because pytest generates a unique `tmp_path` per test, but the global singleton is being stomped twice per test invocation. This is fragile.

3. NO TYPE-COERCION TESTS: No tests verifying Pydantic's coercion behavior for YAML-realistic inputs like `enabled: yes` or string numbers.

4. NO INVALID-TYPE TESTS: No tests for what happens when a user puts nonsensical types in YAML.

5. NO RELATIONSHIP VALIDATION BETWEEN max_traces_in_memory AND max_traces_stored: Logically, in-memory should be <= stored, but no cross-field validation exists.

6. MISSING IMMUTABILITY/FROZEN CONFIG: Models are mutable, allowing silent runtime mutation without persistence.

7. MINOR - ALPHABETICAL FIELD ORDER IN config.yml: yaml.dump sorts keys alphabetically rather than logical order (enabled first).
