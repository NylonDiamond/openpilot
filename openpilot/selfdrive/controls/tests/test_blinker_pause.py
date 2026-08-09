import unittest

from openpilot.common.constants import CV
from openpilot.common.realtime import DT_CTRL
from openpilot.selfdrive.controls.lib.blinker_pause import BlinkerPause
from openpilot.selfdrive.controls.lib.desire_helper import LANE_CHANGE_SPEED_MIN

# NOTE: plain unittest.TestCase on purpose. OpenpilotTestCase pulls in Params, which needs a
# compiled libparams_c and so cannot be imported on a dev machine without a full build.

TURN_SPEED = LANE_CHANGE_SPEED_MIN - 10 * CV.MPH_TO_MS
HIGHWAY_SPEED = LANE_CHANGE_SPEED_MIN + 10 * CV.MPH_TO_MS

# mirrors the UI's BLINKER_PAUSE_DELAYS without importing it, since toggles.py pulls in raylib
DELAY_OPTIONS = (0, 1, 2, 3)


def seconds_to_steps(seconds):
  return int(round(seconds / DT_CTRL))


class TestBlinkerPause(unittest.TestCase):
  def setUp(self):
    self.BP = BlinkerPause()
    self.BP.enabled = True
    self.BP.resume_delay = 1.0

  def step(self, one_blinker, v_ego=TURN_SPEED, steps=1, lat_active=True):
    paused = False
    for _ in range(steps):
      paused = self.BP.update(lat_active, one_blinker, v_ego)
    return paused

  # the setting off must behave exactly as the branch did before it existed

  def test_disabled_never_pauses(self):
    self.BP.enabled = False
    for v_ego in (TURN_SPEED, HIGHWAY_SPEED):
      with self.subTest(v_ego=v_ego):
        self.assertFalse(self.step(True, v_ego=v_ego, steps=seconds_to_steps(5)))

  # starting

  def test_signal_below_the_threshold_pauses(self):
    self.assertTrue(self.step(True))

  def test_signal_above_the_threshold_does_not_pause(self):
    # the lane change assist owns the signal up here, so this must stay out of its way
    self.assertFalse(self.step(True, v_ego=HIGHWAY_SPEED, steps=seconds_to_steps(5)))

  def test_hazards_are_not_a_turn_signal(self):
    # controlsd passes leftBlinker != rightBlinker, so hazards arrive as False
    self.assertFalse(self.step(False, steps=seconds_to_steps(5)))

  def test_no_signal_never_pauses(self):
    self.assertFalse(self.step(False, steps=seconds_to_steps(5)))

  # holding. resuming on speed instead would look to desire_helper like a brand new signal,
  # which with the automatic lane change on is enough to start one nobody asked for.

  def test_pause_survives_crossing_the_threshold(self):
    self.assertTrue(self.step(True))
    self.assertTrue(self.step(True, v_ego=HIGHWAY_SPEED, steps=seconds_to_steps(10)))

  def test_pause_holds_for_as_long_as_the_signal_is_on(self):
    self.assertTrue(self.step(True, steps=seconds_to_steps(60)))

  # resuming

  def test_resume_waits_the_configured_delay(self):
    for delay in DELAY_OPTIONS:
      with self.subTest(delay=delay):
        self.setUp()
        self.BP.resume_delay = float(delay)
        self.step(True, steps=seconds_to_steps(2))

        if delay > 0:
          self.assertTrue(self.step(False, steps=seconds_to_steps(delay) - 1), "resumed early")
        self.assertFalse(self.step(False, steps=2), "never resumed")

  def test_zero_delay_resumes_on_the_next_frame(self):
    self.BP.resume_delay = 0.0
    self.step(True, steps=seconds_to_steps(2))
    self.assertFalse(self.step(False))

  def test_signal_returning_during_the_delay_restarts_the_wait(self):
    self.step(True, steps=seconds_to_steps(2))
    self.assertTrue(self.step(False, steps=seconds_to_steps(0.9)))

    # back on well past the point the first wait would have expired
    self.assertTrue(self.step(True, steps=seconds_to_steps(2)))
    self.assertTrue(self.step(False, steps=seconds_to_steps(0.9)))
    self.assertFalse(self.step(False, steps=seconds_to_steps(0.2)))

  # a real disengage must not leave a half spent timer behind

  def test_lateral_going_inactive_clears_the_pause(self):
    self.step(True, steps=seconds_to_steps(2))
    self.assertFalse(self.step(True, lat_active=False))
    self.assertFalse(self.BP.paused)
    self.assertEqual(self.BP.resume_timer, 0.0)

  def test_reengaging_above_the_threshold_does_not_resume_delay(self):
    self.step(True, steps=seconds_to_steps(2))
    self.step(True, lat_active=False, steps=seconds_to_steps(2))
    self.assertFalse(self.step(True, v_ego=HIGHWAY_SPEED))


if __name__ == "__main__":
  unittest.main()
