import unittest
from types import SimpleNamespace

from openpilot.common.constants import CV
from openpilot.common.realtime import DT_MDL
from openpilot.selfdrive.controls.lib.desire_helper import DesireHelper, LaneChangeState, LANE_CHANGE_SPEED_MIN

# NOTE: plain unittest.TestCase on purpose. OpenpilotTestCase pulls in Params, which needs a
# compiled libparams_c and so cannot be imported on a dev machine without a full build.

HIGHWAY_SPEED = LANE_CHANGE_SPEED_MIN + 10 * CV.MPH_TO_MS


def make_carstate(v_ego=HIGHWAY_SPEED, left_blinker=False, right_blinker=False,
                  steering_pressed=False, steering_torque=0.0,
                  left_blindspot=False, right_blindspot=False):
  return SimpleNamespace(vEgo=v_ego, leftBlinker=left_blinker, rightBlinker=right_blinker,
                         steeringPressed=steering_pressed, steeringTorque=steering_torque,
                         leftBlindspot=left_blindspot, rightBlindspot=right_blindspot)


def seconds_to_steps(seconds):
  return int(round(seconds / DT_MDL))


class TestDesireHelper(unittest.TestCase):
  def setUp(self):
    self.DH = DesireHelper()

  def step(self, carstate, steps=1, lateral_active=True):
    for _ in range(steps):
      self.DH.update(carstate, lateral_active, 0.0)
    return self.DH.lane_change_state

  # nudge mode must behave exactly as it did before the setting existed

  def test_nudge_mode_never_starts_on_its_own(self):
    self.DH.auto_lane_change_delay = 0.0
    cs = make_carstate(left_blinker=True)
    self.assertEqual(self.step(cs, steps=seconds_to_steps(10)), LaneChangeState.preLaneChange)

  def test_nudge_mode_starts_on_torque(self):
    self.DH.auto_lane_change_delay = 0.0
    self.step(make_carstate(left_blinker=True), steps=10)
    nudged = make_carstate(left_blinker=True, steering_pressed=True, steering_torque=1.0)
    self.assertEqual(self.step(nudged), LaneChangeState.laneChangeStarting)

  # automatic mode

  def test_auto_starts_after_the_delay(self):
    self.DH.auto_lane_change_delay = 1.0
    cs = make_carstate(left_blinker=True)

    # one step to enter preLaneChange, then just short of the delay
    self.assertEqual(self.step(cs, steps=seconds_to_steps(0.9)), LaneChangeState.preLaneChange)
    self.assertEqual(self.step(cs, steps=seconds_to_steps(0.2)), LaneChangeState.laneChangeStarting)

  def test_auto_respects_the_configured_delay(self):
    for delay in (1.0, 2.0, 3.0):
      with self.subTest(delay=delay):
        self.DH = DesireHelper()
        self.DH.auto_lane_change_delay = delay
        cs = make_carstate(right_blinker=True)

        self.assertEqual(self.step(cs, steps=seconds_to_steps(delay - 0.2)), LaneChangeState.preLaneChange)
        self.assertEqual(self.step(cs, steps=seconds_to_steps(0.4)), LaneChangeState.laneChangeStarting)

  def test_torque_still_starts_immediately_in_auto_mode(self):
    self.DH.auto_lane_change_delay = 3.0
    self.step(make_carstate(left_blinker=True))
    nudged = make_carstate(left_blinker=True, steering_pressed=True, steering_torque=1.0)
    self.assertEqual(self.step(nudged), LaneChangeState.laneChangeStarting)

  # safety interlocks

  def test_blindspot_blocks_auto_lane_change(self):
    self.DH.auto_lane_change_delay = 1.0
    blocked = make_carstate(left_blinker=True, left_blindspot=True)
    self.assertEqual(self.step(blocked, steps=seconds_to_steps(5)), LaneChangeState.preLaneChange)

  def test_blindspot_resets_the_timer(self):
    self.DH.auto_lane_change_delay = 1.0
    clear = make_carstate(left_blinker=True)
    blocked = make_carstate(left_blinker=True, left_blindspot=True)

    # almost there, then a car appears and the wait starts over
    self.step(clear, steps=seconds_to_steps(0.9))
    self.step(blocked)
    self.assertEqual(self.DH.lane_change_state, LaneChangeState.preLaneChange)

    # clearing the blindspot must not start it instantly, the full delay applies again
    self.assertEqual(self.step(clear, steps=seconds_to_steps(0.5)), LaneChangeState.preLaneChange)
    self.assertEqual(self.step(clear, steps=seconds_to_steps(0.6)), LaneChangeState.laneChangeStarting)

  def test_torque_does_not_start_with_a_car_in_the_blindspot(self):
    # upstream behavior, guards the `and not blindspot_detected` on the start condition.
    # the auto path alone cannot cover this since the timer resets while the blindspot is occupied.
    for delay in (0.0, 1.0):
      with self.subTest(delay=delay):
        self.DH = DesireHelper()
        self.DH.auto_lane_change_delay = delay
        nudged = make_carstate(left_blinker=True, steering_pressed=True, steering_torque=1.0, left_blindspot=True)
        self.assertEqual(self.step(nudged, steps=seconds_to_steps(5)), LaneChangeState.preLaneChange)

  def test_blindspot_on_the_other_side_is_ignored(self):
    self.DH.auto_lane_change_delay = 1.0
    cs = make_carstate(left_blinker=True, right_blindspot=True)
    self.assertEqual(self.step(cs, steps=seconds_to_steps(1.5)), LaneChangeState.laneChangeStarting)

  def test_below_min_speed_never_arms(self):
    self.DH.auto_lane_change_delay = 1.0
    cs = make_carstate(v_ego=LANE_CHANGE_SPEED_MIN - 1.0, left_blinker=True)
    self.assertEqual(self.step(cs, steps=seconds_to_steps(5)), LaneChangeState.off)

  def test_lateral_inactive_never_arms(self):
    self.DH.auto_lane_change_delay = 1.0
    cs = make_carstate(left_blinker=True)
    self.assertEqual(self.step(cs, steps=seconds_to_steps(5), lateral_active=False), LaneChangeState.off)

  def test_cancelling_the_blinker_returns_to_off(self):
    self.DH.auto_lane_change_delay = 3.0
    self.step(make_carstate(left_blinker=True), steps=seconds_to_steps(1))
    self.assertEqual(self.step(make_carstate()), LaneChangeState.off)


if __name__ == "__main__":
  unittest.main()
