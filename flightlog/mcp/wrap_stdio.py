"""Stdio wrapper to capture MCP JSON-RPC traffic."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from threading import Lock, Thread
from typing import Literal
from uuid import uuid4

from flightlog.mcp.storage import append_message, transcript_path
from flightlog.mcp.utils import parse_jsonrpc_payload


def run_wrap(name: str, cmd: list[str], output_root: Path) -> tuple[int, Path]:
    if not cmd:
        raise ValueError("No command provided to wrap")

    session_id = str(uuid4())
    transcript = transcript_path(output_root, name, session_id)
    write_lock = Lock()

    process = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
    )

    stdin_pipe = process.stdin
    stdout_pipe = process.stdout
    stderr_pipe = process.stderr
    if stdin_pipe is None or stdout_pipe is None or stderr_pipe is None:
        raise RuntimeError("Unable to initialize stdio pipes for wrapped process")

    def capture(direction: Literal["client->server", "server->client"], chunk: bytes) -> None:
        text = chunk.decode("utf-8", errors="replace")
        messages = parse_jsonrpc_payload(direction, text)
        if not messages:
            return
        with write_lock:
            for message in messages:
                append_message(transcript, message)

    def forward_stdin() -> None:
        while True:
            line = sys.stdin.buffer.readline()
            if not line:
                break
            stdin_pipe.write(line)
            stdin_pipe.flush()
            capture("client->server", line)
        stdin_pipe.close()

    def forward_stdout() -> None:
        while True:
            line = stdout_pipe.readline()
            if not line:
                break
            sys.stdout.buffer.write(line)
            sys.stdout.buffer.flush()
            capture("server->client", line)

    def forward_stderr() -> None:
        while True:
            line = stderr_pipe.readline()
            if not line:
                break
            sys.stderr.buffer.write(line)
            sys.stderr.buffer.flush()

    threads = [
        Thread(target=forward_stdin, daemon=True),
        Thread(target=forward_stdout, daemon=True),
        Thread(target=forward_stderr, daemon=True),
    ]
    for thread in threads:
        thread.start()

    return_code = process.wait()
    for thread in threads:
        thread.join(timeout=1.0)

    return return_code, transcript
