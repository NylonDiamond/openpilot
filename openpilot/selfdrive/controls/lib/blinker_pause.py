from openpilot.common.realtime import DT_CTRL

# mph, higher than this car goes, so the pause is not limited by speed at all
ANY_SPEED_MPH = 200

# mph below which a turn signal hands the wheel back, 0 is off. the UI writes one of these
# straight into the param, so the stored value says what it means. 20 is LANE_CHANGE_SPEED_MIN,
# the speed desire_helper refuses a lane change below, so it is the one setting that cannot
# collide with the lane change assist
BLINKER_PAUSE_SPEEDS_MPH = (0, 20, 40, ANY_SPEED_MPH)

# degrees at the wheel. how close the driver's steering has to be to openpilot's before handing
# the wheel back is a no-op. latcontrol_angle treats 2.5 as the point where its own command counts
# as met, and this sits looser than that because the model is only being watched here, not followed
RESUME_ANGLE_ERROR = 5.0

# seconds the two have to agree for. modelV2 arrives at 20 Hz and this loop runs at 100, so a bare
# threshold test flickers across the boundary on a road with any texture to it
RESUME_SETTLE_TIME = 0.2

# seconds. ceiling on the whole wait, measured from the signal cancelling. a model that never
# agrees with the driver cannot sit on the steering indefinitely; past this the configured delay
# is all that is left, which is what this did before it watched the wheel at all
MAX_RESUME_DELAY = 5.0


class BlinkerPause:
  """Hands steering back to the driver while a turn signal is on.

  A turn signal at a junction, a driveway or a slip road means a turn openpilot was never
  going to make. It holds the lane straight through all of them and the driver steers against
  it the whole way. Releasing lateral for the length of the signal is the whole feature.

  Which signals count is a speed setting, because above LANE_CHANGE_SPEED_MIN the same signal
  can just as easily mean a lane change, and nothing here can tell the two apart. Below that
  speed desire_helper refuses a lane change outright, so a pause limited to 20 mph cannot
  collide with the lane change assist at all. Setting it higher covers turns off faster roads
  and gives up automatic lane changes below whatever speed is chosen, since desire_helper drops
  straight out of preLaneChange when lateral goes inactive. That trade is the driver's to make,
  which is why it is a setting rather than a fixed number.

  Once started it holds until the signal cancels, at any speed. Ending it on speed instead
  would hand steering back with the signal still on, and desire_helper would read that as a
  brand new signal, since prev_one_blinker is only set while lateral is active. With the
  automatic lane change on that is enough to start a lane change nobody asked for.

  Resuming waits on the turn rather than only on the clock. The signal cancels as the wheel
  comes back through center, which is the middle of a turn and not the end of one, so a fixed
  delay can hand the wheel back with the driver still turning. clip_curvature then unwinds the
  difference at the ISO jerk limit, which at 10 m/s is a fifth of a turn of the wheel per
  second, straight against the driver. Instead the pause holds until openpilot's steering and
  the driver's agree, at which point taking the wheel back costs nothing. The configured delay
  becomes the floor on that wait and MAX_RESUME_DELAY the ceiling.
  """

  def __init__(self):
    # selfdrived's opposite number: the owning process reads the params and sets these
    self.max_speed = 0.0
    self.resume_delay = 0.0

    self.paused = False
    self.resume_timer = 0.0
    self.settle_timer = 0.0

  def update(self, lat_active: bool, one_blinker: bool, v_ego: float, angle_error_deg: float | None) -> bool:
    """True while steering should stay paused.

    lat_active is what latActive would be without this, so anything that ends lateral for a
    real reason also clears the pause rather than carrying a half spent timer into the next
    engagement.

    max_speed is in m/s and 0 turns the whole thing off, so the owner converts the setting once
    rather than this comparing mph against a vEgo.

    angle_error_deg is how far the wheel sits from where openpilot would be holding it, or None
    when there is no model to ask.
    """
    if not (self.max_speed > 0.0 and lat_active):
      self.paused = False
      self.resume_timer = 0.0
      self.settle_timer = 0.0
      return False

    if one_blinker and (self.paused or v_ego < self.max_speed):
      self.paused = True
      self.resume_timer = 0.0
      self.settle_timer = 0.0
    elif self.paused:
      self.resume_timer += DT_CTRL

      if angle_error_deg is None:
        # no model, no opinion. fall back to the delay on its own rather than hold the steering
        # off against an angle nothing is updating
        self.settle_timer = RESUME_SETTLE_TIME
      elif abs(angle_error_deg) <= RESUME_ANGLE_ERROR:
        self.settle_timer += DT_CTRL
      else:
        self.settle_timer = 0.0

      waited = self.resume_timer >= self.resume_delay
      turn_over = self.settle_timer >= RESUME_SETTLE_TIME or self.resume_timer >= MAX_RESUME_DELAY
      self.paused = not (waited and turn_over)

    return self.paused
