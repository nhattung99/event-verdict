"""Narrow Windows workaround for gltest's stdin temporary-file cleanup.

The published 0.29.2 wheel unlinks a file still open through fd 0.
Only that cleanup statement is deferred; contract exceptions are untouched.
"""
import inspect
import os
from pathlib import Path
import textwrap

import pytest

_DEFERRED = []


def _unlink_message_file(path):
    try:
        os.unlink(path)
    except PermissionError as exc:
        if os.name != "nt" or exc.winerror != 32:
            raise
        _DEFERRED.append(path)


@pytest.fixture(scope="session", autouse=True)
def windows_stdin_cleanup():
    if os.name != "nt":
        yield
        return
    from gltest.direct import loader
    original = loader._inject_message_to_fd0
    source = textwrap.dedent(inspect.getsource(original))
    namespace = dict(original.__globals__)
    namespace["_unlink_message_file"] = _unlink_message_file
    source = source.replace("os.unlink(path)", "_unlink_message_file(path)")
    exec(compile(source, inspect.getsourcefile(original), "exec"), namespace)
    loader._inject_message_to_fd0 = namespace[original.__name__]
    try:
        yield
    finally:
        loader._inject_message_to_fd0 = original
        for path in _DEFERRED:
            Path(path).unlink(missing_ok=True)
        _DEFERRED.clear()
