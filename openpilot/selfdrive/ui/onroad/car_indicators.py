from dataclasses import dataclass

import pyray as rl

from openpilot.common.filter_simple import FirstOrderFilter
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.application import gui_app
from openpilot.system.ui.widgets import Widget


@dataclass(frozen=True)
class IndicatorConfig:
  arrow_width: int = 104
  arrow_height: int = 96
  # from screen centre to the inner edge of each arrow. must clear the current speed readout,
  # whose widest realistic case ("188") measures 163px either side of centre.
  arrow_gap: int = 210
  # matches the absolute y hud_renderer uses for the current speed, so the arrows sit level with it
  arrow_center_y: int = 180

  brake_width: int = 320
  brake_height: int = 14
  brake_y: int = 350        # below the speed unit text and clear of the header gradient
  brake_roundness: float = 1.0
  brake_segments: int = 10


@dataclass(frozen=True)
class IndicatorColors:
  TRACK = rl.Color(0, 0, 0, 166)
  BRAKE = rl.Color(231, 96, 96, 255)


CONFIG = IndicatorConfig()
COLORS = IndicatorColors()

# below this a brake command reads as noise rather than the stock system actually slowing the car
BRAKE_DEADZONE = 0.02

# anything fainter than this is invisible, so skip the draw entirely
MIN_VISIBLE_ALPHA = 0.01


class CarIndicators(Widget):
  """Turn signal arrows, and a bar showing brake commanded by the stock ADAS.

  On cars where openpilot does not control longitudinal, stockBrakeCommand is the only
  way to see the stock system braking. carState.brakePressed is the driver's pedal only.
  """

  def __init__(self):
    super().__init__()
    self._left = False
    self._right = False
    self._brake = 0.0

    dt = 1 / gui_app.target_fps
    self._left_filter = FirstOrderFilter(0.0, 0.08, dt)
    self._right_filter = FirstOrderFilter(0.0, 0.08, dt)
    self._brake_filter = FirstOrderFilter(0.0, 0.10, dt)

    # the right arrow is the same asset mirrored at load time, so no second png is needed
    self._txt_left = gui_app.texture('icons_mici/onroad/turn_signal_left.png', CONFIG.arrow_width, CONFIG.arrow_height)
    self._txt_right = gui_app.texture('icons_mici/onroad/turn_signal_left.png', CONFIG.arrow_width, CONFIG.arrow_height, flip_x=True)

  def _update_state(self) -> None:
    sm = ui_state.sm
    if sm.recv_frame["carState"] < ui_state.started_frame:
      self._left = False
      self._right = False
      self._brake = 0.0
      return

    car_state = sm['carState']
    self._left = car_state.leftBlinker
    self._right = car_state.rightBlinker
    self._brake = car_state.stockBrakeCommand

  def _render(self, rect: rl.Rectangle) -> None:
    self.draw(rect, self._left, self._right, self._brake)

  def draw(self, rect: rl.Rectangle, left: bool, right: bool, brake: float) -> None:
    """Drawing only, so a preview harness can drive it without a running SubMaster.

    Advances the fade filters, so call it exactly once per frame.
    """
    left_alpha = self._left_filter.update(1.0 if left else 0.0)
    right_alpha = self._right_filter.update(1.0 if right else 0.0)
    brake_level = self._brake_filter.update(brake if brake > BRAKE_DEADZONE else 0.0)

    center_x = rect.x + rect.width / 2
    arrow_y = CONFIG.arrow_center_y - CONFIG.arrow_height / 2

    if left_alpha > MIN_VISIBLE_ALPHA:
      pos = rl.Vector2(center_x - CONFIG.arrow_gap - CONFIG.arrow_width, arrow_y)
      rl.draw_texture_ex(self._txt_left, pos, 0.0, 1.0, rl.Color(255, 255, 255, int(255 * left_alpha)))

    if right_alpha > MIN_VISIBLE_ALPHA:
      pos = rl.Vector2(center_x + CONFIG.arrow_gap, arrow_y)
      rl.draw_texture_ex(self._txt_right, pos, 0.0, 1.0, rl.Color(255, 255, 255, int(255 * right_alpha)))

    if brake_level > MIN_VISIBLE_ALPHA:
      track = rl.Rectangle(center_x - CONFIG.brake_width / 2, CONFIG.brake_y, CONFIG.brake_width, CONFIG.brake_height)
      rl.draw_rectangle_rounded(track, CONFIG.brake_roundness, CONFIG.brake_segments, COLORS.TRACK)

      # keep the fill at least as wide as it is tall, otherwise the rounded ends degenerate
      fill_width = max(CONFIG.brake_height, track.width * min(1.0, brake_level))
      fill = rl.Rectangle(track.x, track.y, fill_width, track.height)
      rl.draw_rectangle_rounded(fill, CONFIG.brake_roundness, CONFIG.brake_segments, COLORS.BRAKE)
