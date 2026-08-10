import unittest

from openpilot.common.constants import CV
from openpilot.common.realtime import DT_CTRL
from openpilot.selfdrive.controls.lib.blinker_pause import (ANY_SPEED_MPH, BLINKER_PAUSE_SPEEDS_MPH,
                                                            BlinkerPause, MAX_RESUME_DELAY,
                                                            RESUME_ANGLE_ERROR, RESUME_SETTLE_TIME)
from openpilot.selfdrive.controls.lib.desire_helper import LANE_CHANGE_SPEED_MIN

# NOTE: plain unittest.TestCase on purpose. OpenpilotTestCase pulls in Params, which needs a
# compiled libparams_c and so cannot be imported on a dev machine without a full build.

# the default setting, and speeds either side of it
PAUSE_SPEED = 20 * CV.MPH_TO_MS
TURN_SPEED = PAUSE_SPEED - 10 * CV.MPH_TO_MS
HIGHWAY_SPEED = PAUSE_SPEED + 10 * CV.MPH_TO_MS

# mirrors the UI's BLINKER_PAUSE_DELAYS without importing it, since toggles.py pulls in raylib
DELAY_OPTIONS = (0, 1, 2, 3)

# the wheel where openpilot wants it, and the wheel still well into a turn. deliberately not
# written in terms of RESUME_ANGLE_ERROR: a fixture that scales with the constant it is policing
# cannot notice the constant growing wide enough to call a turn finished
AGREED = 0.0
TURNING = 45.0

# frames of either side of a deadline to leave alone. the timers accumulate DT_CTRL, so 500 steps
# reach 4.999999999999938 rather than 5, and a frame exact assertion is testing float noise
SLACK = 5


def seconds_to_steps(seconds):
  return int(round(seconds / DT_CTRL))


class TestBlinkerPause(unittest.TestCase):
  def setUp(self):
    self.BP = BlinkerPause()
    self.BP.max_speed = PAUSE_SPEED
    self.BP.resume_delay = 1.0

  def step(self, one_blinker, v_ego=TURN_SPEED, steps=1, lat_active=True, angle_error=AGREED):
    paused = False
    for _ in range(steps):
      paused = self.BP.update(lat_active, one_blinker, v_ego, angle_error)
    return paused

  def pause(self):
    self.step(True, steps=seconds_to_steps(2))

  # the setting off must behave exactly as the branch did before it existed

  def test_off_never_pauses(self):
    self.BP.max_speed = 0.0
    for v_ego in (TURN_SPEED, HIGHWAY_SPEED):
      with self.subTest(v_ego=v_ego):
        self.assertFalse(self.step(True, v_ego=v_ego, steps=seconds_to_steps(5)))

  def test_off_stays_off_in_reverse(self):
    # vEgo is signed, controlsd tests standstill with abs(), so backing up is a negative speed.
    # off has to be off rather than a threshold that every negative speed happens to be under
    self.BP.max_speed = 0.0
    self.assertFalse(self.step(True, v_ego=-2.0, steps=seconds_to_steps(5)))

  # starting

  def test_signal_below_the_threshold_pauses(self):
    self.assertTrue(self.step(True))

  def test_signal_above_the_threshold_does_not_pause(self):
    # whatever is set, a signal above it is not this setting's business
    self.assertFalse(self.step(True, v_ego=HIGHWAY_SPEED, steps=seconds_to_steps(5)))

  # the speed setting. above 20 mph a signal could mean a lane change instead, so how far up
  # to take it is the driver's call, and the options have to actually differ from each other.

  def test_the_setting_moves_the_threshold(self):
    # the speed that does nothing on the default setting has to pause on the next one up
    self.assertFalse(self.step(True, v_ego=HIGHWAY_SPEED, steps=seconds_to_steps(2)))

    self.setUp()
    self.BP.max_speed = 40 * CV.MPH_TO_MS
    self.assertTrue(self.step(True, v_ego=HIGHWAY_SPEED))

  def test_any_speed_pauses_on_the_motorway(self):
    self.BP.max_speed = ANY_SPEED_MPH * CV.MPH_TO_MS
    self.assertTrue(self.step(True, v_ego=80 * CV.MPH_TO_MS))

  def test_the_settings_are_off_then_ascending(self):
    self.assertEqual(BLINKER_PAUSE_SPEEDS_MPH[0], 0, "the first position has to be off")
    speeds = BLINKER_PAUSE_SPEEDS_MPH[1:]
    self.assertEqual(list(speeds), sorted(set(speeds)), "the positions have to differ and ascend")

  def test_the_safe_setting_is_the_lane_change_minimum(self):
    # 20 mph is the one setting that cannot collide with the lane change assist, because
    # desire_helper refuses a lane change below it. that is only true while the two numbers match
    self.assertAlmostEqual(BLINKER_PAUSE_SPEEDS_MPH[1] * CV.MPH_TO_MS, LANE_CHANGE_SPEED_MIN)

  def test_any_speed_is_past_anything_the_car_does(self):
    self.assertGreater(ANY_SPEED_MPH * CV.MPH_TO_MS, 100 * CV.MPH_TO_MS)

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

  def test_a_cranked_wheel_does_not_hold_the_pause_open_while_signaling(self):
    # the wheel is always turned mid turn, and the signal is what holds the pause until it cancels
    self.assertTrue(self.step(True, steps=seconds_to_steps(2), angle_error=TURNING))

  # resuming on the clock

  def test_resume_waits_the_configured_delay(self):
    for delay in DELAY_OPTIONS:
      with self.subTest(delay=delay):
        self.setUp()
        self.BP.resume_delay = float(delay)
        self.pause()

        if delay > 0:
          self.assertTrue(self.step(False, steps=seconds_to_steps(delay) - SLACK), "resumed early")
        self.assertFalse(self.step(False, steps=seconds_to_steps(RESUME_SETTLE_TIME) + 2 * SLACK), "never resumed")

  def test_zero_delay_resumes_as_soon_as_the_wheel_has_settled(self):
    self.BP.resume_delay = 0.0
    self.pause()
    self.assertTrue(self.step(False, steps=seconds_to_steps(RESUME_SETTLE_TIME) - SLACK), "resumed early")
    self.assertFalse(self.step(False, steps=2 * SLACK), "never resumed")

  def test_signal_returning_restarts_the_wait_on_the_wheel_too(self):
    # a flick, a second thought, another flick. the wheel has to settle again from scratch, or the
    # leftovers of the first wait pay for the second one
    self.BP.resume_delay = 0.0
    self.pause()
    self.assertTrue(self.step(False, steps=seconds_to_steps(RESUME_SETTLE_TIME) - SLACK))

    self.assertTrue(self.step(True, steps=seconds_to_steps(0.5)))
    self.assertTrue(self.step(False, steps=SLACK + 1), "the first wait paid for the second")

  def test_signal_returning_during_the_delay_restarts_the_wait(self):
    self.pause()
    self.assertTrue(self.step(False, steps=seconds_to_steps(0.9)))

    # back on well past the point the first wait would have expired
    self.assertTrue(self.step(True, steps=seconds_to_steps(2)))
    self.assertTrue(self.step(False, steps=seconds_to_steps(0.9)))
    self.assertFalse(self.step(False, steps=seconds_to_steps(0.2)))

  # resuming on the turn being over. the signal cancels as the wheel comes back through center,
  # which is the middle of a turn, so the delay alone can hand the wheel back mid corner.

  def test_a_wheel_still_in_the_turn_holds_steering_past_the_delay(self):
    self.pause()
    self.assertTrue(self.step(False, steps=seconds_to_steps(3), angle_error=TURNING), "resumed mid turn")

  def test_steering_comes_back_once_the_wheel_catches_up(self):
    self.pause()
    self.assertTrue(self.step(False, steps=seconds_to_steps(3), angle_error=TURNING))
    self.assertTrue(self.step(False, steps=seconds_to_steps(RESUME_SETTLE_TIME) - SLACK), "resumed early")
    self.assertFalse(self.step(False, steps=2 * SLACK), "never resumed")

  def test_the_direction_of_the_error_does_not_matter(self):
    for angle_error in (TURNING, -TURNING):
      with self.subTest(angle_error=angle_error):
        self.setUp()
        self.pause()
        self.assertTrue(self.step(False, steps=seconds_to_steps(3), angle_error=angle_error))

  def test_the_threshold_is_narrower_than_a_turn(self):
    # a junction at 10 m radius is about 190 degrees of wheel on this car, and even its tail is
    # tens of degrees. a threshold up near that would call every turn finished the moment it began
    self.assertLess(RESUME_ANGLE_ERROR, TURNING / 4)

  def test_the_wheel_only_has_to_be_close(self):
    # exactly on the threshold counts, so the constant means what it reads as
    self.pause()
    steps = seconds_to_steps(self.BP.resume_delay) + SLACK
    self.assertFalse(self.step(False, steps=steps, angle_error=RESUME_ANGLE_ERROR))

  def test_a_moment_of_agreement_is_not_enough(self):
    # modelV2 lands at 20 Hz against this loop's 100, so the error crossing the threshold for an
    # instant says nothing. only the wheel sitting there does
    self.pause()
    for _ in range(20):
      self.assertTrue(self.step(False, steps=seconds_to_steps(RESUME_SETTLE_TIME) - SLACK, angle_error=AGREED))
      self.assertTrue(self.step(False, steps=SLACK, angle_error=TURNING))

  def test_the_wait_is_capped(self):
    # a model that never agrees with the driver must not sit on the steering forever
    self.pause()
    self.assertTrue(self.step(False, steps=seconds_to_steps(MAX_RESUME_DELAY) - SLACK, angle_error=TURNING), "gave up early")
    self.assertFalse(self.step(False, steps=2 * SLACK, angle_error=TURNING), "never gave up")

  def test_no_model_falls_back_to_the_delay_alone(self):
    self.pause()
    self.assertTrue(self.step(False, steps=seconds_to_steps(self.BP.resume_delay) - SLACK, angle_error=None), "resumed early")
    self.assertFalse(self.step(False, steps=2 * SLACK, angle_error=None), "never resumed")

  # a real disengage must not leave a half spent timer behind

  def test_lateral_going_inactive_clears_the_pause(self):
    self.pause()
    # part way through both waits, so neither timer is trivially zero already
    self.assertTrue(self.step(False, steps=seconds_to_steps(0.5)))
    self.assertGreater(self.BP.settle_timer, 0.0)

    self.assertFalse(self.step(True, lat_active=False))
    self.assertFalse(self.BP.paused)
    self.assertEqual(self.BP.resume_timer, 0.0)
    self.assertEqual(self.BP.settle_timer, 0.0)

  def test_reengaging_above_the_threshold_does_not_resume_delay(self):
    self.pause()
    self.step(True, lat_active=False, steps=seconds_to_steps(2))
    self.assertFalse(self.step(True, v_ego=HIGHWAY_SPEED))


if __name__ == "__main__":
  unittest.main()
