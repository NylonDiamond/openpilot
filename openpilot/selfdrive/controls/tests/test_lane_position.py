import unittest

import numpy as np

from openpilot.common.transformations.model import get_warp_matrix, medmodel_intrinsics
from openpilot.selfdrive.controls.lib.lane_position import (LanePosition, DEFAULT_CAMERA_HEIGHT,
                                                            LANE_POSITION_OFFSETS_CM, LANE_POSITION_SMOOTHING,
                                                            MAX_LANE_POSITION, MIN_CAMERA_HEIGHT)

# NOTE: plain unittest.TestCase on purpose. OpenpilotTestCase pulls in Params, which needs a
# compiled libparams_c and so cannot be imported on a dev machine without a full build.

# a plausible road camera. the exact numbers do not matter, because the tests invert the same
# projection they build, so a sign or scale error in the shear cannot cancel itself out
INTRINSICS = np.array([
  [2648.0, 0.0, 960.0],
  [0.0, 2648.0, 540.0],
  [0.0, 0.0, 1.0],
])

MODEL_FL = medmodel_intrinsics[0, 0]
MODEL_CX = medmodel_intrinsics[0, 2]
MODEL_CY = medmodel_intrinsics[1, 2]

# rpyCalib values to run the geometry against. a mount is never perfectly square to the road, and
# the offset has to be the same sideways step whichever way this one happens to sit
CALIBRATIONS = {
  "level": (0.0, 0.0, 0.0),
  "pitched down": (0.0, 0.04, 0.0),
  "pitched up and yawed": (0.0, -0.03, 0.02),
  "rolled": (0.05, 0.0, 0.0),
  "all three": (0.03, 0.04, -0.02),
}

# model pixels that land on the road rather than the sky. the model frame's horizon sits near the
# top of its 512x256 crop, so anything well down the image is looking at tarmac
ROAD_PIXELS = ((256.0, 120.0), (300.0, 200.0), (120.0, 250.0))


def warp_for(calibration=(0.0, 0.0, 0.0)):
  return get_warp_matrix(np.array(calibration, dtype=np.float32), INTRINSICS, False)


def road_point(model_pixel, height=DEFAULT_CAMERA_HEIGHT):
  """Where on the road a model pixel is looking, as (meters ahead, meters right).

  The model frame is the one calibration has leveled against the road, so this holds whatever the
  mount is doing.
  """
  u, v = model_pixel
  ahead = MODEL_FL * height / (v - MODEL_CY)
  return ahead, (u - MODEL_CX) * ahead / MODEL_FL


def sampled_from(warp, sheared, model_pixel):
  """The model pixel a sheared warp actually ends up sampling, in the plain warp's own frame."""
  camera_pixel = sheared @ np.array([model_pixel[0], model_pixel[1], 1.0])
  p = np.linalg.inv(warp) @ camera_pixel
  return p[0] / p[2], p[1] / p[2]


def settle(lp, lat_active=True, frames=200):
  for _ in range(frames):
    lp.update(lat_active)
  return lp.offset


class TestLanePosition(unittest.TestCase):
  def setUp(self):
    self.lp = LanePosition()

  def offset_lane_position(self):
    self.lp.set_target_cm(LANE_POSITION_OFFSETS_CM[0])
    settle(self.lp)
    return self.lp.offset

  def test_starts_centered(self):
    self.assertEqual(self.lp.target, 0.0)
    self.assertEqual(self.lp.offset, 0.0)

  def test_centimeters_become_meters(self):
    self.lp.set_target_cm(10)
    self.assertAlmostEqual(self.lp.target, 0.10)

  def test_target_is_clamped_both_ways(self):
    self.lp.set_target_cm(500)
    self.assertEqual(self.lp.target, MAX_LANE_POSITION)
    self.lp.set_target_cm(-500)
    self.assertEqual(self.lp.target, -MAX_LANE_POSITION)

  def test_every_setting_position_survives_the_clamp(self):
    # a button whose value the cap silently swallows would be a position that does nothing
    for offset_cm in LANE_POSITION_OFFSETS_CM:
      self.lp.set_target_cm(offset_cm)
      self.assertAlmostEqual(self.lp.target, offset_cm * 0.01)

  def test_the_offset_ramps_in_rather_than_stepping(self):
    self.lp.set_target_cm(LANE_POSITION_OFFSETS_CM[0])
    first = self.lp.update(True)
    self.assertGreater(first, 0.0)
    self.assertLess(first, self.lp.target)
    self.assertAlmostEqual(first, LANE_POSITION_SMOOTHING * self.lp.target)

  def test_the_ramp_reaches_the_target_and_stops_there(self):
    self.lp.set_target_cm(LANE_POSITION_OFFSETS_CM[0])
    self.assertAlmostEqual(settle(self.lp), self.lp.target, places=4)
    self.assertAlmostEqual(self.lp.update(True), self.lp.target, places=4)

  def test_the_ramp_never_overshoots(self):
    self.lp.set_target_cm(LANE_POSITION_OFFSETS_CM[0])
    for _ in range(200):
      self.assertLessEqual(self.lp.update(True), self.lp.target)

  def test_nothing_is_applied_while_openpilot_is_not_steering(self):
    self.lp.set_target_cm(LANE_POSITION_OFFSETS_CM[0])
    self.assertEqual(settle(self.lp, lat_active=False), 0.0)

  def test_an_established_offset_ramps_back_out_on_disengage(self):
    self.lp.set_target_cm(LANE_POSITION_OFFSETS_CM[0])
    settle(self.lp)
    self.assertAlmostEqual(settle(self.lp, lat_active=False), 0.0, places=4)

  def test_a_centered_setting_leaves_the_warp_alone(self):
    warp = warp_for()
    np.testing.assert_allclose(self.lp.warp(warp, medmodel_intrinsics, DEFAULT_CAMERA_HEIGHT), warp, atol=1e-4)

  def test_the_shear_is_the_view_from_a_camera_moved_sideways(self):
    # the invariant the whole feature rests on. at every distance down the road, and whatever the
    # mount is doing, the sheared warp samples a point exactly `offset` further across than the
    # plain one and no further along it. anything but a lateral step of the viewpoint fails one
    offset = self.offset_lane_position()

    for name, calibration in CALIBRATIONS.items():
      with self.subTest(calibration=name):
        warp = warp_for(calibration)
        sheared = self.lp.warp(warp, medmodel_intrinsics, DEFAULT_CAMERA_HEIGHT)

        for model_pixel in ROAD_PIXELS:
          ahead, right = road_point(model_pixel)
          ahead_sheared, right_sheared = road_point(sampled_from(warp, sheared, model_pixel))

          self.assertGreater(ahead, 0.0, "test pixel is looking at the sky, not the road")
          self.assertAlmostEqual(ahead_sheared, ahead, places=3)
          self.assertAlmostEqual(right_sheared - right, offset, places=3)

  def test_a_positive_offset_puts_the_car_left_of_center(self):
    # follows from the test above. the model is shown the world sitting `offset` to its right, so
    # it decides the lane is over there and steers until the lane it can see is centered, leaving
    # the car itself that far to the left. this is the sign convention the whole setting hangs on
    self.offset_lane_position()

    warp = warp_for()
    sheared = self.lp.warp(warp, medmodel_intrinsics, DEFAULT_CAMERA_HEIGHT)

    _, right = road_point(ROAD_PIXELS[1])
    _, right_sheared = road_point(sampled_from(warp, sheared, ROAD_PIXELS[1]))

    self.assertGreater(LANE_POSITION_OFFSETS_CM[0], 0)
    self.assertGreater(right_sheared, right)

  def test_the_shear_scales_with_camera_height(self):
    # the offset is a distance on the road, so the same shift in the image buys twice as much of
    # it from half the height. reading the measured height rather than assuming one matters
    self.offset_lane_position()
    warp = warp_for()

    tall = self.lp.warp(warp, medmodel_intrinsics, DEFAULT_CAMERA_HEIGHT)
    short = self.lp.warp(warp, medmodel_intrinsics, DEFAULT_CAMERA_HEIGHT / 2)

    _, right = road_point(ROAD_PIXELS[1])
    _, right_tall = road_point(sampled_from(warp, tall, ROAD_PIXELS[1]))
    _, right_short = road_point(sampled_from(warp, short, ROAD_PIXELS[1]))

    self.assertAlmostEqual(right_short - right, 2 * (right_tall - right), places=3)

  def test_an_uncalibrated_height_cannot_blow_up_the_shear(self):
    self.offset_lane_position()
    warp = warp_for()

    floored = self.lp.warp(warp, medmodel_intrinsics, MIN_CAMERA_HEIGHT)
    np.testing.assert_allclose(self.lp.warp(warp, medmodel_intrinsics, 0.0), floored)

  def test_the_setting_positions_run_left_to_right(self):
    # the buttons sit in this order on screen, so the values behind them have to descend
    self.assertEqual(list(LANE_POSITION_OFFSETS_CM), sorted(LANE_POSITION_OFFSETS_CM, reverse=True))
    self.assertEqual(LANE_POSITION_OFFSETS_CM[len(LANE_POSITION_OFFSETS_CM) // 2], 0)


if __name__ == "__main__":
  unittest.main()
