import unittest
from types import SimpleNamespace

from openpilot.common.constants import CV
from openpilot.selfdrive.controls.lib.curve_advisory import (CurveAdvisory, CURVE_ADVISORY_HYSTERESIS,
                                                             CURVE_ADVISORY_MIN_SPEED, CURVE_ADVISORY_THRESHOLDS,
                                                             LOOKAHEAD_MAX_T, LOOKAHEAD_MIN_T)

# NOTE: plain unittest.TestCase on purpose. OpenpilotTestCase pulls in Params, which needs a
# compiled libparams_c and so cannot be imported on a dev machine without a full build.

# mirrors ModelConstants.T_IDXS without importing modeld, which pulls in numpy and the model stack
T_IDXS = [10.0 * ((idx / 32) ** 2) for idx in range(33)]

TEST_SPEED = CURVE_ADVISORY_MIN_SPEED + 15 * CV.MPH_TO_MS
CRAWL_SPEED = CURVE_ADVISORY_MIN_SPEED - 5 * CV.MPH_TO_MS

OFF, LATE, NORMAL, EARLY = 0, 1, 2, 3


def curvature_for(lateral_accel, v_ego=TEST_SPEED):
  """The path curvature that asks for this much lateral accel at this speed."""
  return lateral_accel / (v_ego ** 2)


def make_model(curvature=0.0, v_model=TEST_SPEED, t_min=LOOKAHEAD_MIN_T, t_max=LOOKAHEAD_MAX_T):
  """A model message whose path bends at `curvature` between t_min and t_max.

  The model publishes yaw rate, which is curvature times the speed it expects to be doing.
  """
  yaw_rates = [curvature * v_model if t_min <= t <= t_max else 0.0 for t in T_IDXS]
  return SimpleNamespace(
    orientationRate=SimpleNamespace(t=list(T_IDXS), z=yaw_rates),
    velocity=SimpleNamespace(x=[v_model] * len(T_IDXS)),
  )


def make_carstate(v_ego=TEST_SPEED):
  return SimpleNamespace(vEgo=v_ego)


class TestCurveAdvisory(unittest.TestCase):
  def setUp(self):
    self.CA = CurveAdvisory()
    self.CA.level = NORMAL

  def step(self, model, carstate=None, steps=1):
    for _ in range(steps):
      result = self.CA.update(model, carstate if carstate is not None else make_carstate())
    return result

  # the setting off must behave exactly as the branch did before it existed
  def test_off_never_warns(self):
    self.CA.level = OFF
    violent = make_model(curvature_for(10.0))
    self.assertFalse(self.step(violent, steps=100))

  def test_a_level_outside_the_table_is_treated_as_off(self):
    for level in (-1, len(CURVE_ADVISORY_THRESHOLDS), 99):
      with self.subTest(level=level):
        self.setUp()
        self.CA.level = level
        self.assertFalse(self.step(make_model(curvature_for(10.0))))

  # the road ahead
  def test_straight_road_never_warns(self):
    self.assertFalse(self.step(make_model(0.0), steps=100))

  def test_sharp_curve_warns(self):
    threshold = CURVE_ADVISORY_THRESHOLDS[NORMAL]
    self.assertTrue(self.step(make_model(curvature_for(threshold + 1.0))))

  def test_gentle_curve_does_not_warn(self):
    threshold = CURVE_ADVISORY_THRESHOLDS[NORMAL]
    self.assertFalse(self.step(make_model(curvature_for(threshold - 1.0))))

  def test_it_warns_on_a_curve_in_either_direction(self):
    threshold = CURVE_ADVISORY_THRESHOLDS[NORMAL]
    for direction in (1, -1):
      with self.subTest(direction=direction):
        self.setUp()
        self.assertTrue(self.step(make_model(direction * curvature_for(threshold + 1.0))))

  # only the stretch of horizon worth warning about
  def test_a_curve_already_underway_does_not_warn(self):
    near = make_model(curvature_for(10.0), t_min=0.0, t_max=LOOKAHEAD_MIN_T / 2)
    self.assertFalse(self.step(near))

  def test_a_curve_beyond_the_horizon_does_not_warn(self):
    far = make_model(curvature_for(10.0), t_min=LOOKAHEAD_MAX_T + 1.0, t_max=T_IDXS[-1])
    self.assertFalse(self.step(far))

  # speed
  def test_below_the_speed_floor_never_warns(self):
    crawl = make_carstate(CRAWL_SPEED)
    # a junction taken at walking pace bends far harder than any road would
    self.assertFalse(self.step(make_model(curvature_for(10.0, CRAWL_SPEED), v_model=CRAWL_SPEED), crawl))

  def test_slowing_below_the_floor_clears_an_active_warning(self):
    model = make_model(curvature_for(CURVE_ADVISORY_THRESHOLDS[NORMAL] + 1.0))
    self.assertTrue(self.step(model))
    self.assertFalse(self.step(model, make_carstate(CRAWL_SPEED)))

  def test_curvature_is_read_off_the_models_own_predicted_speed(self):
    # the model predicts braking into the bend that the driver has not done yet. its yaw rate
    # is tied to that slower speed, so recovering curvature with the current speed instead
    # would read the road as half as tight as it is and stay quiet through it
    threshold = CURVE_ADVISORY_THRESHOLDS[NORMAL]
    predicted = TEST_SPEED / 2
    bend = curvature_for(threshold + 1.0)
    self.assertTrue(self.step(make_model(bend, v_model=predicted), make_carstate(TEST_SPEED)))

  def test_a_model_predicting_acceleration_does_not_overstate_the_bend(self):
    threshold = CURVE_ADVISORY_THRESHOLDS[NORMAL]
    gentle = curvature_for(threshold - 1.0)
    self.assertFalse(self.step(make_model(gentle, v_model=TEST_SPEED * 2), make_carstate(TEST_SPEED)))

  def test_the_same_bend_warns_at_speed_and_not_below_it(self):
    # curvature is a property of the road, so only the speed carried into it changes
    bend = curvature_for(CURVE_ADVISORY_THRESHOLDS[NORMAL] + 1.0)
    self.assertTrue(self.step(make_model(bend)))
    self.setUp()
    slow = TEST_SPEED / 2
    self.assertFalse(self.step(make_model(bend, v_model=slow), make_carstate(slow)))

  # sensitivity
  def test_earlier_levels_warn_on_gentler_curves(self):
    for level in (LATE, NORMAL, EARLY):
      with self.subTest(level=level):
        threshold = CURVE_ADVISORY_THRESHOLDS[level]
        self.setUp()
        self.CA.level = level
        self.assertTrue(self.step(make_model(curvature_for(threshold + 0.1))), "did not warn above its threshold")
        self.setUp()
        self.CA.level = level
        self.assertFalse(self.step(make_model(curvature_for(threshold - 0.1))), "warned below its threshold")

  def test_a_curve_between_two_levels_only_warns_on_the_earlier_one(self):
    between = curvature_for((CURVE_ADVISORY_THRESHOLDS[LATE] + CURVE_ADVISORY_THRESHOLDS[NORMAL]) / 2)
    self.CA.level = LATE
    self.assertFalse(self.step(make_model(between)))
    self.setUp()
    self.CA.level = NORMAL
    self.assertTrue(self.step(make_model(between)))

  # hysteresis, so a bend sitting on the limit does not strobe the banner
  def test_warning_holds_while_the_curve_eases_slightly(self):
    threshold = CURVE_ADVISORY_THRESHOLDS[NORMAL]
    self.assertTrue(self.step(make_model(curvature_for(threshold + 1.0))))
    easing = threshold * (CURVE_ADVISORY_HYSTERESIS + 1.0) / 2  # between the clear point and the threshold
    self.assertTrue(self.step(make_model(curvature_for(easing)), steps=100), "cleared before the hysteresis band")

  def test_warning_clears_once_the_curve_opens_up(self):
    threshold = CURVE_ADVISORY_THRESHOLDS[NORMAL]
    self.assertTrue(self.step(make_model(curvature_for(threshold + 1.0))))
    self.assertFalse(self.step(make_model(curvature_for(threshold * CURVE_ADVISORY_HYSTERESIS - 0.1))))

  def test_hysteresis_does_not_let_a_gentle_curve_trip_it(self):
    # the band only holds an existing warning, it must never start one
    threshold = CURVE_ADVISORY_THRESHOLDS[NORMAL]
    self.assertFalse(self.step(make_model(curvature_for(threshold * CURVE_ADVISORY_HYSTERESIS + 0.1)), steps=100))

  # a model message with nothing in it says nothing about the road
  def test_empty_model_never_warns(self):
    empty = SimpleNamespace(orientationRate=SimpleNamespace(t=[], z=[]), velocity=SimpleNamespace(x=[]))
    self.assertFalse(self.step(empty))

  def test_ragged_model_never_warns(self):
    ragged = SimpleNamespace(orientationRate=SimpleNamespace(t=list(T_IDXS), z=[0.0]),
                             velocity=SimpleNamespace(x=[TEST_SPEED]))
    self.assertFalse(self.step(ragged))

  def test_an_empty_model_clears_an_active_warning(self):
    self.assertTrue(self.step(make_model(curvature_for(CURVE_ADVISORY_THRESHOLDS[NORMAL] + 1.0))))
    empty = SimpleNamespace(orientationRate=SimpleNamespace(t=[], z=[]), velocity=SimpleNamespace(x=[]))
    self.assertFalse(self.step(empty))

  def test_a_model_predicting_a_stop_does_not_divide_by_zero(self):
    stopped = make_model(0.0, v_model=0.0)
    stopped.orientationRate.z = [0.5] * len(T_IDXS)
    self.step(stopped)  # must not raise


if __name__ == "__main__":
  unittest.main()
