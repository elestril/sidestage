from typing import Dict, Any, Optional
from pydantic import BaseModel, Field

class Gametime(BaseModel):
    seconds: int = Field(default=0, description="Total seconds since epoch")

    @classmethod
    def from_seconds(cls, seconds: int) -> "Gametime":
        return cls(seconds=seconds)

    @classmethod
    def from_string(cls, time_str: str) -> "Gametime":
        """
        Parses a string in format 'Day D, HH:MM:SS'
        """
        try:
            # Format: "Day 1, 12:30:00"
            parts = time_str.split(",")
            day_part = parts[0].strip().replace("Day ", "")
            time_part = parts[1].strip()
            
            days = int(day_part)
            h, m, s = map(int, time_part.split(":"))
            
            total_seconds = (days * 24 * 3600) + (h * 3600) + (m * 60) + s
            return cls(seconds=total_seconds)
        except Exception as e:
            raise ValueError(f"Invalid gametime format: {time_str}. Expected 'Day D, HH:MM:SS'") from e

    def to_string(self) -> str:
        """
        Converts to 'Day D, HH:MM:SS'
        """
        days = self.seconds // (24 * 3600)
        remainder = self.seconds % (24 * 3600)
        h = remainder // 3600
        remainder %= 3600
        m = remainder // 60
        s = remainder % 60
        
        return f"Day {days}, {h:02d}:{m:02d}:{s:02d}"

    def __str__(self) -> str:
        return self.to_string()

    def add_seconds(self, seconds: int) -> "Gametime":
        return Gametime(seconds=self.seconds + seconds)
