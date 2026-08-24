"""A ball that rides up a track on the right of the screen as the model gets surer of the scene.

Ported from comma's own comma 4 UI (openpilot/selfdrive/ui/mici/onroad/confidence_ball.py).
Two things had to change on the way over.

The comma 4 draws the ball into a solid black side panel, so it fakes a vertical gradient with a
square and paints the corners out in black. Over a camera image that would leave black corners on
the road, so the ball here is a radial gradient instead, which needs no background to hide behind.

That side panel also gave the ball a frame to be read against. Without one a lone ball floating
over the road says nothing, because there is no telling a high one from a low one. It rides a
faint track here for the same reason a gauge has a dial.
"""

import pyray as rl

from openpilot.common.filter_simple import FirstOrderFilter
from openpilot.selfdrive.ui.ui_state import ui_state, UIStatus
from openpilot.system.ui.lib.application import gui_app
from openpilot.system.ui.widgets import Widget

BALL_RADIUS = 30

# the blind spot bar owns the last 40px of the edge, so the ball sits inboard of it with enough
# gap that a lit bar and the ball never read as one object
BALL_INSET = 116

# the top of the travel clears the experimental button, whether or not it is being drawn. a track
# whose length depends on a setting is a gauge that means something different on Tuesday.
TRACK_TOP = 252
TRACK_BOTTOM_MARGIN = 72

TRACK_WIDTH = 6
TRACK_COLOR = rl.Color(255, 255, 255, 60)

# parked below the bottom of the track, which is where the ball waits while openpilot is not
# steering. it rises out of the floor on engage rather than appearing from nowhere.
PARKED = -0.5

CONFIDENCE_TAU = 0.5

# the track goes with the ball. an empty gauge left on screen while openpilot is not steering is
# clutter reporting nothing, and it is the only part of this that is on screen every drive.
FADE_TAU = 0.3
MIN_VISIBLE_ALPHA = 0.01

# the same three zones the comma 4 uses, so a ball read there reads the same here
HIGH_CONFIDENCE = 0.5
MEDIUM_CONFIDENCE = 0.2

COLORS = {
  'high': (rl.Color(0, 255, 204, 255), rl.Color(0, 255, 38, 255)),
  'medium': (rl.Color(255, 200, 0, 255), rl.Color(255, 115, 0, 255)),
  'low': (rl.Color(255, 0, 21, 255), rl.Color(255, 0, 89, 255)),
  'override': (rl.Color(255, 255, 255, 255), rl.Color(82, 82, 82, 255)),
  'off': (rl.Color(50, 50, 50, 255), rl.Color(13, 13, 13, 255)),
}


class ConfidenceBall(Widget):
  def __init__(self):
    super().__init__()
    dt = 1 / gui_app.target_fps
    self._confidence_filter = FirstOrderFilter(PARKED, CONFIDENCE_TAU, dt)
    self._fade_filter = FirstOrderFilter(0.0, FADE_TAU, dt)

  def _update_state(self) -> None:
    sm = ui_state.sm
    stale = sm.recv_frame['modelV2'] < ui_state.started_frame
    steering = not stale and ui_state.status != UIStatus.DISENGAGED
    self._fade_filter.update(1.0 if steering else 0.0)

    if not steering:
      self._confidence_filter.update(PARKED)
      return

    # the model's own read on whether the driver is about to take it back. the comma 4 leaves gas
    # out of this and so does this, which happens to suit a car openpilot never drives with.
    predictions = sm['modelV2'].meta.disengagePredictions
    brake = max(predictions.brakeDisengageProbs or [1])
    steer = max(predictions.steerOverrideProbs or [1])
    self._confidence_filter.update((1 - brake) * (1 - steer))

  def _render(self, rect: rl.Rectangle) -> None:
    alpha = self._fade_filter.x
    if alpha < MIN_VISIBLE_ALPHA:
      return

    confidence = self._confidence_filter.x

    top = rect.y + TRACK_TOP
    bottom = rect.y + rect.height - TRACK_BOTTOM_MARGIN
    center_x = rect.x + rect.width - BALL_INSET

    self._draw_track(center_x, top, bottom, alpha)

    # the travel is inset by the radius at both ends so a full or empty ball sits inside the track
    travel_top = top + BALL_RADIUS
    travel_bottom = bottom - BALL_RADIUS
    center_y = travel_bottom - confidence * (travel_bottom - travel_top)

    inner, outer = self._colors(confidence)
    rl.draw_circle_gradient(rl.Vector2(center_x, center_y), BALL_RADIUS,
                            self._faded(inner, alpha), self._faded(outer, alpha))

  @staticmethod
  def _faded(color: rl.Color, alpha: float) -> rl.Color:
    return rl.Color(color.r, color.g, color.b, int(color.a * alpha))

  @staticmethod
  def _draw_track(center_x: float, top: float, bottom: float, alpha: float) -> None:
    track = rl.Rectangle(center_x - TRACK_WIDTH / 2, top, TRACK_WIDTH, bottom - top)
    rl.draw_rectangle_rounded(track, 1.0, 6, ConfidenceBall._faded(TRACK_COLOR, alpha))

  @staticmethod
  def _colors(confidence: float) -> tuple[rl.Color, rl.Color]:
    if ui_state.status == UIStatus.OVERRIDE:
      return COLORS['override']
    if ui_state.status != UIStatus.ENGAGED:
      return COLORS['off']
    if confidence > HIGH_CONFIDENCE:
      return COLORS['high']
    if confidence > MEDIUM_CONFIDENCE:
      return COLORS['medium']
    return COLORS['low']
