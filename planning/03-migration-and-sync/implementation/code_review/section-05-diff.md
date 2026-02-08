# Section 05 Diff: Validator

## New file: src/sidestage/migration/validator.py

Implements `validate_parse_result()` which checks referential integrity and required fields
in parsed campaign data. Returns a `MigrationValidationReport`.

Validation steps:
1. Build lookup indices (entity_ids, location_ids, item_ids, scene_ids)
2. Check entity ID uniqueness
3. Check entity cross-references (Character->Location, Character->Item, Location->Location, Scene->Location, Event->Scene)
4. Check required entity fields (id, name non-empty)
5. Check memory references (owner_id, target_id exist; memory_type valid; required fields non-empty)
6. Add data-loss warning
7. Carry forward parse errors/warnings from ParseResult
8. Build and return MigrationValidationReport

## New file: tests/unit/test_migration_validator.py

15 tests covering:
- Valid parse result passes (test_validates_successfully_with_correct_references)
- Duplicate entity IDs detected
- Character location/inventory references validated
- Location connected_locations references validated
- Scene location_id references validated
- Event scene_id references validated
- Required entity fields checked (empty id)
- Memory owner_id/target_id references validated
- Memory with null owner_id allowed
- Invalid memory_type detected
- Missing required memory fields detected
- Data-loss warning always included
- Errors vs warnings distinction
