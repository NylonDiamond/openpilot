import numpy as np


# lateral offset in centimeters for each setting position, positive sits the car left of center.
# the UI writes one of these straight into the param, so the stored value says what it means
LANE_POSITION_OFFSETS_CM = (20, 10, 0, -10, -20)

# meters. the shear leans vertical objects in the model's 512x256 crop, and far enough past this
# the model starts losing confidence in the scene it is being shown. the same mechanism is capped
# at 0.35 m elsewhere for that reason, and nothing here needs to go near it
MAX_LANE_POSITION = 0.20

# fraction of the remaining distance covered each model frame. at 20 Hz this settles in a bit over
# half a second, so the car slides across the lane rather than stepping across it
LANE_POSITION_SMOOTHING = 0.1

# meters. extrinsicsCalibration measures the camera height, but not before it has calibrated. this is
# the same figure calibrationd starts from, HEIGHT_INIT in calibrationd.py
DEFAULT_CAMERA_HEIGHT = 1.22
MIN_CAMERA_HEIGHT = 0.5


class LanePosition:
  """Biases where in the lane the car sits, by moving the camera the model thinks it has.

  openpilot drives this car end to end. The model looks at the road and emits one curvature,
  and there is no planner left to shift a path in, nor any lane position for a controller to
  close a loop around. Both were deleted upstream when lane planning went away.

  So rather than argue with the model, this lies to it. A camera moved sideways over a flat road
  produces an image sheared about the horizon, by the sideways distance over the camera height.
  Applying that shear to the warp that feeds the model hands it the view from a camera that is
  not where the camera is. It goes on centering itself in the lane exactly as before, and the
  car ends up parked to one side of where it believes it is.

  Nothing downstream changes: no new controller, no feedback term, no interaction with the
  steering limits. The offset also holds through a curve, because it is geometry rather than a
  constant added to curvature, which is where the cheap version of this feature comes apart.

  The cost is that the shear is a lie about the image as well as the viewpoint. Vertical objects
  lean, and far enough out the model gets less sure of what it is looking at. Hence the cap.
  """

  def __init__(self):
    # modeld's opposite number: the owning process reads the param and sets this
    self.target = 0.0

    self.offset = 0.0

  def set_target_cm(self, offset_cm: int) -> None:
    self.target = min(max(offset_cm * 0.01, -MAX_LANE_POSITION), MAX_LANE_POSITION)

  def update(self, lat_active: bool) -> float:
    """Step the applied offset toward the target and return it, in meters."""
    # there is nothing to offset when openpilot is not the one steering, and ramping back in on
    # engage means the car eases across rather than the model watching its camera jump sideways
    target = self.target if lat_active else 0.0
    self.offset += LANE_POSITION_SMOOTHING * (target - self.offset)
    return self.offset

  def warp(self, model_transform: np.ndarray, model_intrinsics: np.ndarray, height: float) -> np.ndarray:
    """Shear a model warp so it samples the view from `offset` meters to the side.

    `model_transform` maps the model frame to camera pixels, so composing on the right puts the
    shear in the model frame, which calibration has already leveled against the road. Shearing in
    camera pixels instead would pivot about the principal point rather than about the horizon, and
    on a mount with any pitch to it that tilt of the vanishing point reads as a yaw error rather
    than a sideways step. Doing it here means the offset is a translation for any calibration,
    which also keeps calibrationd from slowly absorbing it.
    """
    k = self.offset / max(height, MIN_CAMERA_HEIGHT)
    cy = model_intrinsics[1, 2]

    shear = np.eye(3, dtype=np.float32)
    shear[0, 1] = k
    shear[0, 2] = -k * cy

    return (model_transform @ shear).astype(np.float32)
