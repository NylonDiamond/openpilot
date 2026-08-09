import unittest

from openpilot.common.realtime import DT_CTRL
from openpilot.selfdrive.car.gear_debounce import REVERSE_DEBOUNCE_T, ReverseGearFilter

FRAMES = round(REVERSE_DEBOUNCE_T / DT_CTRL)


class TestReverseGearFilter(unittest.TestCase):
  def test_disabled_passes_input_through(self):
    # the regression guard: switched off, the filter has to be indistinguishable from
    # `CS.gearShifter == reverse`, frame for frame
    f = ReverseGearFilter()
    pattern = [False, True, False, True, True, True, False, False, True]
    self.assertEqual([f.update(r) for r in pattern], pattern)

  def test_enabled_waits_the_full_delay(self):
    f = ReverseGearFilter()
    f.enabled = True
    for i in range(FRAMES - 1):
      self.assertFalse(f.update(True), f"fired early on frame {i}")
    self.assertTrue(f.update(True))

  def test_enabled_stays_true_while_in_reverse(self):
    f = ReverseGearFilter()
    f.enabled = True
    for _ in range(FRAMES):
      f.update(True)
    for _ in range(200):
      self.assertTrue(f.update(True))

  def test_transit_through_reverse_never_fires(self):
    # what the shifter actually does going from drive to park: a few frames of reverse
    f = ReverseGearFilter()
    f.enabled = True
    for _ in range(FRAMES - 1):
      self.assertFalse(f.update(True))
    self.assertFalse(f.update(False))

  def test_leaving_reverse_resets_the_count(self):
    # a near miss must not leave credit behind for the next one
    f = ReverseGearFilter()
    f.enabled = True
    for _ in range(FRAMES - 1):
      f.update(True)
    f.update(False)
    for i in range(FRAMES - 1):
      self.assertFalse(f.update(True), f"fired early on frame {i} of the second attempt")
    self.assertTrue(f.update(True))

  def test_delay_is_one_tenth_of_a_second(self):
    self.assertAlmostEqual(FRAMES * DT_CTRL, 0.1)


if __name__ == "__main__":
  unittest.main()
