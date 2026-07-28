"""Narrow logging configuration for the human-auth diagnostic channel.

WHY THIS EXISTS (Checkpoint 28)
-------------------------------
Helios emitted safe auth-rejection reason codes that were invisible in hosted
logs. Render starts the app with plain ``uvicorn app.main:app`` (no
``--log-config``, no ``--log-level``), and uvicorn's ``LOGGING_CONFIG`` declares
only the ``uvicorn``, ``uvicorn.error`` and ``uvicorn.access`` loggers — it has
no ``root`` key, and ``Config.configure_logging()`` calls ``setLevel`` only on
``uvicorn.*``. The root logger therefore keeps Python's defaults: level WARNING
and no handlers.

Two independent consequences, either sufficient to lose the record:

* ``helios.auth.human`` had no explicit level, so its effective level was
  inherited from root (WARNING). ``logger.info(...)`` failed
  ``isEnabledFor(INFO)`` and the record was discarded *at the call site* — it
  never reached a handler at all.
* Even at WARNING it would only have reached ``logging.lastResort``, an
  unformatted bare stderr handler.

Uvicorn's own access lines were unaffected because ``uvicorn.access`` owns an
explicit stdout handler at INFO.

DESIGN
------
Configure exactly one logger — ``helios.auth.human`` — with a single stderr
handler at INFO and ``propagate = False``.

* Scoped to the *child*, deliberately. The parent ``helios.auth`` carries the
  machine project-API-key path (``app/security/service.py``), whose INFO records
  include internal key ids. Configuring the parent would newly expose those;
  configuring the child leaves the machine path exactly as it was.
* ``propagate = False`` means a record is handled here and nowhere else, so it
  can never be emitted twice (once here and once via root/``lastResort``).
* Rejection events are additionally emitted at WARNING by the caller, so the
  record clears Python's default threshold and still reaches ``lastResort`` even
  if this function never runs (an alternate ASGI entrypoint, a bare import).
  Either way exactly one record is produced.

This configures no other logger and never raises the global level: DEBUG is
never enabled anywhere.

SAFETY
------
The formatter structurally drops ``exc_info`` and ``stack_info``, so no
exception message, traceback, URL, or credential can reach this stream even if a
future caller passes ``exc_info=True`` by mistake. Only the preformatted
message, level, and logger name are emitted.
"""

from __future__ import annotations

import logging
import sys

#: The one logger this module configures. Deliberately the child of
#: ``helios.auth`` so the machine API-key path is left untouched.
AUTH_LOGGER_NAME = "helios.auth.human"

#: Marks our handler so repeated calls cannot stack duplicates.
_HANDLER_MARKER = "_helios_auth_handler"


class SafeAuthFormatter(logging.Formatter):
    """Formatter that cannot emit exception or stack detail.

    ``logging.Formatter`` appends ``record.exc_text``/``stack_info`` when present.
    Auth diagnostics must never carry exception text (it can embed URLs, JWKS
    responses, or credentials), so both are dropped structurally rather than by
    convention at each call site.
    """

    def format(self, record: logging.LogRecord) -> str:
        # Work on a shallow copy so other handlers observing the same record are
        # unaffected.
        scrubbed = logging.makeLogRecord(record.__dict__)
        scrubbed.exc_info = None
        scrubbed.exc_text = None
        scrubbed.stack_info = None
        return super().format(scrubbed)

    def formatException(self, ei) -> str:  # pragma: no cover - defensive
        return ""

    def formatStack(self, stack_info: str) -> str:  # pragma: no cover - defensive
        return ""


def configure_auth_logging() -> logging.Logger:
    """Make human-auth diagnostics reach the hosted stderr stream.

    Idempotent: safe to call from every ``create_app()`` (tests build many apps)
    without stacking handlers. Returns the configured logger for callers/tests.
    """
    logger = logging.getLogger(AUTH_LOGGER_NAME)

    already_configured = any(
        getattr(handler, _HANDLER_MARKER, False) for handler in logger.handlers
    )
    if not already_configured:
        handler = logging.StreamHandler(stream=sys.stderr)
        handler.setLevel(logging.INFO)
        handler.setFormatter(SafeAuthFormatter("%(levelname)s [%(name)s] %(message)s"))
        setattr(handler, _HANDLER_MARKER, True)
        logger.addHandler(handler)

    logger.setLevel(logging.INFO)
    # Handled here and nowhere else: no duplicate record via root/lastResort.
    logger.propagate = False
    return logger
