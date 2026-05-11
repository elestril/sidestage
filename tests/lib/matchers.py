"""Matchers used by integration scenarios to assert on Scene message lists.

Per `spec-location-pydoc`, the per-class invariants for `Matcher` and the
concrete matchers live in pydoc on this module. The protocol is intentionally
extensible so future LLM-judge matchers slot in without changes upstream.

.implements: testing-matcher
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from sidestage.message import Message


class Matcher(Protocol):
    """matcher-protocol: Asserts on a list of Messages after dispatch.

    Implementations raise AssertionError on failure; return None on pass.
    The protocol is the seam where future LLM-judge matchers slot in
    without disturbing scenarios or the runner.

    .implements: testing-matcher
    """

    def check(self, messages: list[Message]) -> None: ...


@dataclass(frozen=True)
class LastMessage:
    """last-message-matcher: Match the last message after dispatch.

    All non-None fields must match. `body` is exact equality;
    `body_contains` is a substring check; `body_matches` is a `re.search`
    regex check. `sender_id` is matched against `messages[-1].sender.id`.
    Raises AssertionError if the message list is empty.

    .implements: testing-matcher
    """

    sender_id: str | None = None
    body: str | None = None
    body_contains: str | None = None
    body_matches: str | None = None

    def check(self, messages: list[Message]) -> None:
        assert messages, "LastMessage: scene.messages is empty"
        last = messages[-1]
        if self.sender_id is not None:
            assert last.sender.id == self.sender_id, (
                f"LastMessage: sender_id={last.sender.id!r}, "
                f"expected {self.sender_id!r}"
            )
        if self.body is not None:
            assert last.body == self.body, (
                f"LastMessage: body={last.body!r}, expected {self.body!r}"
            )
        if self.body_contains is not None:
            assert self.body_contains in last.body, (
                f"LastMessage: body={last.body!r} does not contain "
                f"{self.body_contains!r}"
            )
        if self.body_matches is not None:
            assert re.search(self.body_matches, last.body) is not None, (
                f"LastMessage: body={last.body!r} does not match regex "
                f"{self.body_matches!r}"
            )


@dataclass(frozen=True)
class Sequence:
    """sequence-matcher: Match a tail sequence of messages — the last N
    matchers run against the last N messages, in order.

    Raises AssertionError if `messages` has fewer than `len(matchers)`
    entries.

    .implements: testing-matcher
    """

    matchers: tuple["Matcher", ...]

    def __init__(self, *matchers: "Matcher") -> None:
        object.__setattr__(self, "matchers", matchers)

    def check(self, messages: list[Message]) -> None:
        n = len(self.matchers)
        assert len(messages) >= n, (
            f"Sequence: need {n} messages, got {len(messages)}"
        )
        tail = messages[-n:] if n > 0 else []
        for i, matcher in enumerate(self.matchers):
            matcher.check(tail[: i + 1])


@dataclass(frozen=True)
class All:
    """all-matcher: Boolean AND — every wrapped matcher must pass.

    .implements: testing-matcher
    """

    matchers: tuple["Matcher", ...]

    def __init__(self, *matchers: "Matcher") -> None:
        object.__setattr__(self, "matchers", matchers)

    def check(self, messages: list[Message]) -> None:
        for matcher in self.matchers:
            matcher.check(messages)


@dataclass(frozen=True)
class Any:  # noqa: A001 — intentional shadow of builtins.Any in this module
    """any-matcher: Boolean OR — at least one wrapped matcher must pass.

    Raises only if every matcher raises AssertionError; aggregates the
    failure messages for diagnosis.

    .implements: testing-matcher
    """

    matchers: tuple["Matcher", ...]

    def __init__(self, *matchers: "Matcher") -> None:
        object.__setattr__(self, "matchers", matchers)

    def check(self, messages: list[Message]) -> None:
        errors: list[str] = []
        for matcher in self.matchers:
            try:
                matcher.check(messages)
                return
            except AssertionError as exc:
                errors.append(str(exc))
        raise AssertionError(
            "Any: every matcher failed:\n  - " + "\n  - ".join(errors)
        )
