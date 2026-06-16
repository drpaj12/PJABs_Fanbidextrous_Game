# src/game/meters.py
"""A fillable meter that fires (and resets) when it reaches its threshold."""


class Meter:
    def __init__(self, threshold: int) -> None:
        self.threshold: int = threshold
        self.value: int = 0

    def add(self, credit: int) -> bool:
        """Add credit. Return True if the meter fired (and was reset)."""
        self.value = max(0, self.value + credit)
        if self.value >= self.threshold:
            self.value = 0
            return True
        return False
