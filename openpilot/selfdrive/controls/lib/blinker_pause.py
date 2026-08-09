from openpilot.common.realtime import DT_CTRL
from openpilot.selfdrive.controls.lib.desire_helper import LANE_CHANGE_SPEED_MIN


class BlinkerPause:
  """Hands steering back to the driver while a turn signal is on.

  Below LANE_CHANGE_SPEED_MIN desire_helper refuses a lane change, so a turn signal down
  there means a junction, a driveway or a slip road. openpilot holds the lane straight
  through all of them and the driver steers against it the whole way. Releasing lateral for
  the length of the signal is the whole feature.

  The pause only starts below that speed, so a signal on the highway still reaches the lane
  change assist untouched and the two settings stay independent.

  Once started it holds until the signal cancels, at any speed. Ending it on speed instead
  would hand steering back with the signal still on, and desire_helper would read that as a
  brand new signal, since prev_one_blinker is only set while lateral is active. With the
  automatic lane change on that is enough to start a lane change nobody asked for.
  """

  def __init__(self):
    # selfdrived's opposite number: the owning process reads the params and sets these
    self.enabled = False
    self.resume_delay = 0.0

    self.paused = False
    self.resume_timer = 0.0

  def update(self, lat_active: bool, one_blinker: bool, v_ego: float) -> bool:
    """True while steering should stay paused.

    lat_active is what latActive would be without this, so anything that ends lateral for a
    real reason also clears the pause rather than carrying a half spent timer into the next
    engagement.
    """
    if not (self.enabled and lat_active):
      self.paused = False
      self.resume_timer = 0.0
      return False

    if one_blinker and (self.paused or v_ego < LANE_CHANGE_SPEED_MIN):
      self.paused = True
      self.resume_timer = 0.0
    elif self.paused:
      self.resume_timer += DT_CTRL
      self.paused = self.resume_timer < self.resume_delay

    return self.paused
