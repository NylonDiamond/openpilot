from openpilot.common.constants import CV


# below this a tight turn is a junction, a slip road or a car park, and the advisory would
# fire on every one of them
CURVE_ADVISORY_MIN_SPEED = 25 * CV.MPH_TO_MS

# the stretch of the model's horizon the advisory reads, in seconds. anything earlier is a
# curve already being steered rather than one to warn about
LOOKAHEAD_MIN_T = 1.5
LOOKAHEAD_MAX_T = 5.0

# lateral accel in m/s^2 the peak of that stretch has to reach, indexed by setting level.
# level 0 is off. ISO 11270 puts a comfortable limit at 3.0, and this car's measured maximum
# is around 2.13, so even the latest setting fires below what the tires are asked for
CURVE_ADVISORY_THRESHOLDS = (0.0, 3.0, 2.5, 2.0)

# fraction of the threshold the curve has to drop back under before the banner clears. a bend
# sitting exactly on the limit would otherwise strobe it
CURVE_ADVISORY_HYSTERESIS = 0.8

# guards the curvature divide where the model predicts a near stop
MIN_SPEED = 1.0


class CurveAdvisory:
  """Warns that the speed being carried into an upcoming curve is high.

  openpilot has no longitudinal control on this car, so this can only ever tell the driver.
  EyeSight holds its set speed into a bend, which is exactly the case the stock system has
  nothing to say about.

  The model publishes a predicted yaw rate across its whole horizon and nothing downstream
  reads it. Dividing that by the model's own predicted speed recovers the curvature of the
  path ahead, which is a property of the road rather than of how fast the car is going.
  Multiplying by current speed then answers the question worth asking: hold this speed, and
  what does that bend ask of the tires.

  Using current speed rather than the predicted speed for that second step is deliberate. The
  model predicts what the car will do, and on a car whose cruise holds speed through curves,
  assuming the slowdown that has not happened yet is how a warning arrives too late.
  """

  def __init__(self):
    # selfdrived's opposite number: the owning process reads the param and sets this
    self.level = 0

    self.warning = False

  def update(self, modelV2, CS) -> bool:
    """True while the driver should be told to slow for what is coming."""
    threshold = 0.0
    if 0 < self.level < len(CURVE_ADVISORY_THRESHOLDS):
      threshold = CURVE_ADVISORY_THRESHOLDS[self.level]

    if threshold <= 0.0 or CS.vEgo < CURVE_ADVISORY_MIN_SPEED:
      self.warning = False
      return False

    orientation_rate = modelV2.orientationRate
    velocity = modelV2.velocity
    ts = orientation_rate.t

    # a model message that has not filled these yet says nothing about the road
    if not len(ts) or len(orientation_rate.z) != len(ts) or len(velocity.x) != len(ts):
      self.warning = False
      return False

    v_ego_sq = CS.vEgo ** 2
    peak_lateral_accel = 0.0
    for i, t in enumerate(ts):
      if not LOOKAHEAD_MIN_T <= t <= LOOKAHEAD_MAX_T:
        continue
      curvature = orientation_rate.z[i] / max(velocity.x[i], MIN_SPEED)
      peak_lateral_accel = max(peak_lateral_accel, abs(curvature) * v_ego_sq)

    if self.warning:
      self.warning = peak_lateral_accel > threshold * CURVE_ADVISORY_HYSTERESIS
    else:
      self.warning = peak_lateral_accel >= threshold

    return self.warning
