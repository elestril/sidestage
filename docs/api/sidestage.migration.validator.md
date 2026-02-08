# `sidestage.migration.validator`

Referential integrity and schema validation for parsed campaign data.

## Functions

### `validate_parse_result(parse_result: ParseResult) -> MigrationValidationReport`

Validate referential integrity and required fields in parsed campaign data.

Args:
    parse_result: Output of parse_directory(), containing entities, memories,
        chatlogs, and parse-level errors.

Returns:
    MigrationValidationReport with valid flag, counts, errors, and warnings.
