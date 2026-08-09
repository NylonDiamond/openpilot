"""Filtering for the transient gear readings a moving shift lever produces.

A gated shifter reports every detent it crosses, so shifting out of drive and into park walks
through neutral and reverse on the way. Reverse shows up for a few tens of milliseconds and is
gone again. Stock openpilot acts on the first frame of reverse, which is right when the car is
really in reverse and merely noisy when the lever was only passing through.
"""

from openpilot.common.realtime import DT_CTRL

# how long reverse has to hold before it counts, when the filter is switched on
REVERSE_DEBOUNCE_T = 0.1


class ReverseGearFilter:
  def __init__(self):
    self.enabled = False
    self.frames = 0

  def update(self, in_reverse: bool) -> bool:
    """Whether reverse should be acted on. Switched off, this returns `in_reverse` unchanged."""
    self.frames = self.frames + 1 if in_reverse else 0
    required = max(round(REVERSE_DEBOUNCE_T / DT_CTRL), 1) if self.enabled else 1
    return self.frames >= required
