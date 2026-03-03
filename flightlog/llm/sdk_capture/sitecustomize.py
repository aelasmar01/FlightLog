"""Auto-enable SDK capture when imported by Python sitecustomize hook."""

from flightlog.llm.sdk_capture.hook import enable_sdk_capture

enable_sdk_capture(force=False)
