from __future__ import annotations

from datetime import datetime, timedelta, timezone

# Arbitrary in-game epoch: year 1, January 1, midnight UTC.
_EPOCH = datetime(1, 1, 1, tzinfo=timezone.utc)


class Gametime(datetime):
    """Game-world timestamp stored as seconds since an arbitrary epoch.

    Subclasses ``datetime`` so ``timedelta`` arithmetic works naturally.
    Storage representation is always ``int`` (total seconds).
    Display format is ``"Day D, HH:MM:SS"``.
    """

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __new__(cls, *args: object, **kwargs: object) -> Gametime:
        # Convenience: Gametime(seconds=N)
        if not args and "seconds" in kwargs:
            return cls.from_seconds(int(kwargs["seconds"]))  # type: ignore[arg-type]
        return super().__new__(cls, *args, **kwargs)  # type: ignore[arg-type]

    @classmethod
    def from_seconds(cls, seconds: int) -> Gametime:
        """Create a Gametime from total seconds since the game epoch."""
        dt = _EPOCH + timedelta(seconds=seconds)
        return super().__new__(
            cls, dt.year, dt.month, dt.day,
            dt.hour, dt.minute, dt.second,
            dt.microsecond, tzinfo=timezone.utc,
        )

    @classmethod
    def from_string(cls, time_str: str) -> Gametime:
        """Parse ``'Day D, HH:MM:SS'`` format."""
        try:
            parts = time_str.split(",")
            day_part = parts[0].strip().removeprefix("Day ")
            time_part = parts[1].strip()
            days = int(day_part)
            h, m, s = map(int, time_part.split(":"))
            total = (days * 24 * 3600) + (h * 3600) + (m * 60) + s
            return cls.from_seconds(total)
        except Exception as e:
            raise ValueError(
                f"Invalid gametime format: {time_str!r}. Expected 'Day D, HH:MM:SS'"
            ) from e

    # ------------------------------------------------------------------
    # Conversion
    # ------------------------------------------------------------------

    def total_seconds(self) -> int:
        """Return total seconds since the game epoch (for storage)."""
        delta = self - _EPOCH.replace(tzinfo=self.tzinfo or timezone.utc)
        return int(delta.total_seconds())

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def __str__(self) -> str:
        secs = self.total_seconds()
        days = secs // (24 * 3600)
        remainder = secs % (24 * 3600)
        h = remainder // 3600
        remainder %= 3600
        m = remainder // 60
        s = remainder % 60
        return f"Day {days}, {h:02d}:{m:02d}:{s:02d}"

    def __repr__(self) -> str:
        return f"Gametime(seconds={self.total_seconds()})"

    # ------------------------------------------------------------------
    # Arithmetic — keep results as Gametime when they are datetimes
    # ------------------------------------------------------------------

    def __add__(self, other: object) -> Gametime | timedelta:  # type: ignore[override]
        result = super().__add__(other)  # type: ignore[arg-type]
        if isinstance(result, datetime) and not isinstance(result, Gametime):
            return Gametime(
                result.year, result.month, result.day,
                result.hour, result.minute, result.second,
                result.microsecond, tzinfo=result.tzinfo,
            )
        return result  # type: ignore[return-value]

    def __radd__(self, other: object) -> Gametime | timedelta:  # type: ignore[override]
        return self.__add__(other)

    def __sub__(self, other: object) -> Gametime | timedelta:  # type: ignore[override]
        result = super().__sub__(other)  # type: ignore[arg-type]
        # datetime - datetime → timedelta (leave as-is)
        # datetime - timedelta → datetime (wrap as Gametime)
        if isinstance(result, datetime) and not isinstance(result, Gametime):
            return Gametime(
                result.year, result.month, result.day,
                result.hour, result.minute, result.second,
                result.microsecond, tzinfo=result.tzinfo,
            )
        return result  # type: ignore[return-value]
