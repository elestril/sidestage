"""@action decorator + per-class action registry.

A method decorated with `@action` is marked as RPC-callable. The
`WsConnection.entity_action` dispatcher checks
`action_name in type(entity)._actions` before invoking; bare methods
on Entity subclasses are in-process-only.

Per `specs/backend.md` `backend-action-decorator`.
"""

from __future__ import annotations


def action[F](method: F) -> F:
    """Mark `method` as RPC-callable.

    Sets `__sidestage_action__ = True` on the method object. `Entity`'s
    `__init_subclass__` walks each subclass for methods carrying this
    marker and builds `_actions: set[str]` accordingly.

    .implements: backend-action-marks-method, backend-action-class-level
    """
    method.__sidestage_action__ = True  # type: ignore[attr-defined]
    return method
