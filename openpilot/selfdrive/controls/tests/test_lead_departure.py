import unittest
from types import SimpleNamespace

from openpilot.common.realtime import DT_CTRL
from openpilot.selfdrive.controls.lib.lead_departure import (ARM_TIME, DEPART_DISTANCE, LEAD_DEPART_SPEED,
                                                             LEAD_STOPPED_SPEED, LeadDeparture,
                                                             MAX_LEAD_DISTANCE, MIN_LEAD_PROB, STOPPED_SPEED)

# NOTE: plain unittest.TestCase on purpose. OpenpilotTestCase pulls in Params, which needs a
# compiled libparams_c and so cannot be imported on a dev machine without a full build.

STOP_DISTANCE = 8.0
ARM_FRAMES = int(ARM_TIME / DT_CTRL) + 2


def radar_state(present=True, distance=STOP_DISTANCE, speed=0.0, prob=1.0):
  return SimpleNamespace(leadOne=SimpleNamespace(present=present, dRel=distance, vLead=speed, modelProb=prob))


def car_state(speed=0.0):
  return SimpleNamespace(vEgo=speed)


class TestLeadDeparture(unittest.TestCase):
  def setUp(self):
    self.ld = LeadDeparture(DT_CTRL)
    self.ld.enabled = True

  def arm(self, distance=STOP_DISTANCE):
    """Sit still behind a still lead until the alert is armed. Asserts nothing fires on the way."""
    for _ in range(ARM_FRAMES):
      self.assertFalse(self.ld.update(radar_state(distance=distance), car_state()))

  def run_frames(self, n, **lead):
    """Returns how many of the n frames fired."""
    return sum(self.ld.update(radar_state(**lead), car_state()) for _ in range(n))

  # --- the happy path ---

  def test_fires_when_the_stopped_lead_pulls_away(self):
    self.arm()
    departed = radar_state(distance=STOP_DISTANCE + DEPART_DISTANCE + 1.0, speed=LEAD_DEPART_SPEED + 1.0)
    self.assertTrue(self.ld.update(departed, car_state()))

  def test_fires_exactly_once(self):
    self.arm()
    fired = self.run_frames(50, distance=STOP_DISTANCE + DEPART_DISTANCE + 1.0, speed=LEAD_DEPART_SPEED + 1.0)
    self.assertEqual(fired, 1)

  def test_rearms_after_moving_off(self):
    self.arm()
    self.assertTrue(self.ld.update(radar_state(distance=STOP_DISTANCE + DEPART_DISTANCE + 1.0,
                                               speed=LEAD_DEPART_SPEED + 1.0), car_state()))

    # drive away, then join the back of the next queue
    for _ in range(100):
      self.ld.update(radar_state(distance=20.0, speed=10.0), car_state(speed=10.0))

    self.arm()
    self.assertTrue(self.ld.update(radar_state(distance=STOP_DISTANCE + DEPART_DISTANCE + 1.0,
                                               speed=LEAD_DEPART_SPEED + 1.0), car_state()))

  # --- what must not fire ---

  def test_silent_while_disabled(self):
    self.ld.enabled = False
    for _ in range(ARM_FRAMES):
      self.ld.update(radar_state(), car_state())
    self.assertFalse(self.ld.update(radar_state(distance=STOP_DISTANCE + DEPART_DISTANCE + 1.0,
                                                speed=LEAD_DEPART_SPEED + 1.0), car_state()))

  def test_silent_before_armed(self):
    # one frame short of armed, then an unmistakable departure
    for _ in range(int(ARM_TIME / DT_CTRL) - 2):
      self.ld.update(radar_state(), car_state())
    self.assertFalse(self.ld.update(radar_state(distance=STOP_DISTANCE + DEPART_DISTANCE + 1.0,
                                                speed=LEAD_DEPART_SPEED + 1.0), car_state()))

  def test_silent_while_we_are_moving(self):
    # rolling up to a queue: the gap opens and closes the whole way in
    fired = 0
    for distance in (30.0, 25.0, 20.0, 24.0, 18.0, 22.0, 10.0):
      for _ in range(ARM_FRAMES):
        fired += self.ld.update(radar_state(distance=distance, speed=LEAD_DEPART_SPEED + 1.0),
                                car_state(speed=STOPPED_SPEED + 1.0))
    self.assertEqual(fired, 0)

  def test_silent_when_the_gap_barely_moves(self):
    self.arm()
    fired = self.run_frames(200, distance=STOP_DISTANCE + DEPART_DISTANCE - 0.5, speed=LEAD_DEPART_SPEED + 1.0)
    self.assertEqual(fired, 0)

  def test_silent_when_the_lead_is_too_slow_to_be_leaving(self):
    self.arm()
    fired = self.run_frames(200, distance=STOP_DISTANCE + DEPART_DISTANCE + 5.0, speed=LEAD_DEPART_SPEED - 0.2)
    self.assertEqual(fired, 0)

  def test_never_arms_behind_a_lead_that_never_stopped(self):
    fired = 0
    for _ in range(ARM_FRAMES * 3):
      fired += self.ld.update(radar_state(speed=LEAD_STOPPED_SPEED + 0.5), car_state())
    self.assertEqual(fired, 0)

  def test_silent_with_no_lead(self):
    self.arm()
    fired = self.run_frames(200, present=False, distance=STOP_DISTANCE + DEPART_DISTANCE + 5.0,
                            speed=LEAD_DEPART_SPEED + 1.0)
    self.assertEqual(fired, 0)

  def test_silent_when_the_model_is_unsure_of_the_lead(self):
    self.arm()
    fired = self.run_frames(200, distance=STOP_DISTANCE + DEPART_DISTANCE + 5.0,
                            speed=LEAD_DEPART_SPEED + 1.0, prob=MIN_LEAD_PROB - 0.1)
    self.assertEqual(fired, 0)

  def test_ignores_scenery_beyond_the_lead_range(self):
    far = MAX_LEAD_DISTANCE + 5.0
    fired = 0
    for _ in range(ARM_FRAMES * 2):
      fired += self.ld.update(radar_state(distance=far), car_state())
    self.assertEqual(fired, 0)

  # --- the case the distance anchor exists for ---

  def test_measures_from_the_closest_point_not_the_first_one(self):
    """A lead that shuffles forward before it goes must not spend the margin doing it."""
    self.arm(distance=12.0)

    # creeps 3 m closer over a couple of seconds, still stopped by our reckoning
    for distance in (11.0, 10.0, 9.0):
      for _ in range(50):
        self.assertFalse(self.ld.update(radar_state(distance=distance), car_state()))

    # back out to where it started is not a departure, because the anchor moved in with it
    self.assertFalse(self.ld.update(radar_state(distance=9.0 + DEPART_DISTANCE - 0.5,
                                                speed=LEAD_DEPART_SPEED + 1.0), car_state()))
    # past the anchor by the full margin is
    self.assertTrue(self.ld.update(radar_state(distance=9.0 + DEPART_DISTANCE + 0.5,
                                               speed=LEAD_DEPART_SPEED + 1.0), car_state()))


if __name__ == "__main__":
  unittest.main()
