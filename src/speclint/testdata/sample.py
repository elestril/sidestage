"""sample: A tiny module-level docstring for tests."""

from __future__ import annotations


class SampleClass:
    """sample-class: A class with one labeled invariant.

    - sample-class-greet: Returns a fixed greeting string.
    """

    def greet(self) -> str:
        """sample-class-greet: Returns the literal 'hi'."""
        return "hi"
