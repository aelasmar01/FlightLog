from flightlog.redaction import redact_artifacts


def test_redaction_regex_json_and_exclusion() -> None:
    config = {
        "regex_rules": [
            {
                "name": "token",
                "pattern": r"(token=)([A-Za-z0-9]+)",
                "mask_groups": [2],
                "replacement": "***",
            }
        ],
        "json_keys": ["api_key"],
        "exclude_paths": ["private/*"],
    }
    artifacts = {
        "notes.txt": "token=abcdef",
        "data.json": '{"api_key":"secret","nested":{"api_key":"secret2"}}',
        "private/file.txt": "should not be included",
    }

    redacted, report = redact_artifacts(artifacts, config)

    assert "private/file.txt" not in redacted
    assert "private/file.txt" in report.excluded_artifacts
    assert redacted["notes.txt"].decode("utf-8") == "token=***"
    assert '"api_key":"***REDACTED***"' in redacted["data.json"].decode("utf-8")
    assert report.patterns_matched["token"] == 1
    assert report.json_keys_masked["api_key"] == 2
