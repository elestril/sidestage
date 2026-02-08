# Code Review Interview: Section 02 - Serialization

**Date:** 2026-02-07

## Auto-Fixes

1. **Add ChatMessage to entity roundtrip test.** ChatMessage has a model_validator that could interfere with roundtrip — worth testing.

## Let Go

- sanitize_filename trailing underscore deviation: implementation behavior matches spec description ("strips leading/trailing underscores")
- Scene messages silently dropped: intentional per plan (chatlog.log)
- Scene events field included: consistent with plan
- Detailed docstrings omitted: keeping code concise
- ChatMessage widget dict: edge case, address later if needed
- Memory field ordering: not required by plan
- Copy vs mutate: implementation correctly copies first
