# Flightlog Pack Schema Versioning Policy

## Version format

Pack schemas use [Semantic Versioning](https://semver.org/): `MAJOR.MINOR.PATCH`.

The current version is defined in `flightlog/schema_version.py`.

## What triggers each component

| Component | Triggers |
|-----------|----------|
| **MAJOR** | Removing required fields, renaming top-level keys in `manifest.json` or `timeline.jsonl`, changing hash algorithm, breaking timeline line format |
| **MINOR** | Adding optional top-level fields to manifest or timeline events, adding new `type` values, adding new artifact sections |
| **PATCH** | Documentation clarifications, no schema changes |

## Compatibility guarantees

- **MINOR and PATCH bumps are backward-compatible.** A reader that understands `1.0.0` can safely read a `1.1.x` pack (unknown fields are ignored).
- **MAJOR bumps are breaking.** `validate` rejects packs with a different MAJOR version by default; pass `--allow-major` to override and attempt validation anyway.

## Validation behavior

```
flightlog pack validate --path <pack>
```

- Accepts packs where the stored `schema_version` MAJOR == current MAJOR and stored MINOR >= 0.
- Rejects packs where MAJOR differs, unless `--allow-major` is supplied (warning is still printed).
- Rejects packs with non-semver version strings.

## No automatic upgrade

There is no auto-upgrade tool. If you need to reprocess a pack written under an old schema:

1. Re-run `flightlog pack build` against the original log inputs, OR
2. Manually adjust `manifest.json` and re-hash affected fields.

## Adding new schema features

When adding new optional fields to the timeline or manifest:

1. Add the field to the Pydantic model with a default.
2. Bump the MINOR version in `schema_version.py`.
3. Update `SUPPORTED_SCHEMA_VERSIONS` if you want to keep accepting older packs.
4. Add a test confirming both old and new versions validate successfully.

## History

| Version | Change |
|---------|--------|
| 1.0.0   | Initial release |
