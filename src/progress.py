"""
Progress hooks for long pipeline steps.

The pipeline calls `report()`; a front-end (the CLI) may register a listener with
`set_listener()` to display it. Without a listener every call is a no-op, so the
web app and the tests are unaffected.

Stages are short stable keys ("coauthors_openalex"), not display text: the
front-end owns the wording and the language.
"""
from __future__ import annotations

from typing import Callable, Optional

Listener = Callable[[str, Optional[int], Optional[int]], None]

_listener: Optional[Listener] = None


def set_listener(listener: Optional[Listener]) -> None:
    global _listener
    _listener = listener


def report(stage: str, done: Optional[int] = None, total: Optional[int] = None) -> None:
    """Signal that `stage` started, or advanced to `done` out of `total`."""
    if _listener is None:
        return
    try:
        _listener(stage, done, total)
    except Exception:
        # Displaying progress must never break an analysis
        pass
