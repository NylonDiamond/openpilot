from dataclasses import dataclass

import pyray as rl

from openpilot.common.filter_simple import FirstOrderFilter
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.application import gui_app, FontWeight
from openpilot.system.ui.lib.multilang import tr
from openpilot.system.ui.lib.text_measure import measure_text_cached
from openpilot.system.ui.widgets import Widget


@dataclass(frozen=True)
class IndicatorConfig:
  arrow_width: int = 104
  arrow_height: int = 96
  # from screen center to the inner edge of each arrow. must clear the current speed readout,
  # whose widest realistic case ("188") measures 163px either side of center.
  arrow_gap: int = 210
  # matches the absolute y hud_renderer uses for the current speed, so the arrows sit level with it
  arrow_center_y: int = 180

  brake_width: int = 320
  brake_height: int = 14
  brake_y: int = 350        # below the speed unit text and clear of the header gradient
  brake_roundness: float = 1.0
  brake_segments: int = 10

  # the lateral-only badge sits directly under the set speed box, so it reads as part of it.
  # these mirror hud_renderer's _draw_set_speed, which is the thing being qualified.
  set_speed_x: int = 60
  set_speed_y: int = 45
  set_speed_width_metric: int = 200
  set_speed_width_imperial: int = 172
  set_speed_height: int = 204
  lat_only_gap: int = 12
  lat_only_height: int = 76
  lat_only_font: int = 26

  # blind spot bars, hard against the sides so they read peripherally rather than needing a look
  bsm_width: int = 12
  bsm_height: int = 360
  bsm_inset: int = 28
  bsm_roundness: float = 1.0
  bsm_segments: int = 6


@dataclass(frozen=True)
class IndicatorColors:
  TRACK = rl.Color(0, 0, 0, 166)
  BRAKE = rl.Color(231, 96, 96, 255)
  # amber rather than the engaged green: openpilot is on, but doing less than usual
  LAT_ONLY = rl.Color(255, 179, 0, 255)
  LAT_ONLY_BG = rl.Color(0, 0, 0, 166)
  # the same caution amber, so a tinted arrow and a lit side bar read as one thing
  BSM = rl.Color(255, 179, 0, 255)


CONFIG = IndicatorConfig()
COLORS = IndicatorColors()

# below this a brake command reads as noise rather than the stock system actually slowing the car
BRAKE_DEADZONE = 0.02

# anything fainter than this is invisible, so skip the draw entirely
MIN_VISIBLE_ALPHA = 0.01


class CarIndicators(Widget):
  """Turn signal arrows, a bar showing brake commanded by the stock ADAS, and a badge for
  when openpilot is steering without the stock cruise underneath it.

  On cars where openpilot does not control longitudinal, stockBrakeCommand is the only
  way to see the stock system braking. carState.brakePressed is the driver's pedal only.

  With MADS, cruiseState.enabled is a latch that outlives the stock ACC, so the rest of the
  screen looks identical whether or not anything is managing speed. stockCruiseEngaged is
  the raw state, and the gap between the two is exactly what the badge reports.
  """

  def __init__(self):
    super().__init__()
    self._left = False
    self._right = False
    self._brake = 0.0
    self._lat_only = False
    self._bsm_left = False
    self._bsm_right = False

    dt = 1 / gui_app.target_fps
    self._left_filter = FirstOrderFilter(0.0, 0.08, dt)
    self._right_filter = FirstOrderFilter(0.0, 0.08, dt)
    self._brake_filter = FirstOrderFilter(0.0, 0.10, dt)
    self._lat_only_filter = FirstOrderFilter(0.0, 0.15, dt)
    self._bsm_left_filter = FirstOrderFilter(0.0, 0.10, dt)
    self._bsm_right_filter = FirstOrderFilter(0.0, 0.10, dt)

    self._font_semi_bold: rl.Font = gui_app.font(FontWeight.SEMI_BOLD)

    # the right arrow is the same asset mirrored at load time, so no second png is needed
    self._txt_left = gui_app.texture('icons_mici/onroad/turn_signal_left.png', CONFIG.arrow_width, CONFIG.arrow_height)
    self._txt_right = gui_app.texture('icons_mici/onroad/turn_signal_left.png', CONFIG.arrow_width, CONFIG.arrow_height, flip_x=True)

  def _update_state(self) -> None:
    sm = ui_state.sm
    if sm.recv_frame["carState"] < ui_state.started_frame:
      self._left = False
      self._right = False
      self._brake = 0.0
      self._lat_only = False
      self._bsm_left = False
      self._bsm_right = False
      return

    # each element is switchable on its own. feeding a disabled one its off value rather than
    # skipping the draw lets it fade out the way it normally would, and keeps draw() a pure
    # function of its arguments for the preview harness.
    car_state = sm['carState']
    signals = ui_state.show_turn_signals
    self._left = car_state.leftBlinker and signals
    self._right = car_state.rightBlinker and signals
    self._brake = car_state.stockBrakeCommand if ui_state.show_stock_brake else 0.0
    self._lat_only = (car_state.cruiseState.enabled and not car_state.stockCruiseEngaged
                      and ui_state.show_steering_only)
    blind_spot = ui_state.show_blind_spot
    self._bsm_left = car_state.leftBlindspot and blind_spot
    self._bsm_right = car_state.rightBlindspot and blind_spot

  def _render(self, rect: rl.Rectangle) -> None:
    self.draw(rect, self._left, self._right, self._brake, self._lat_only, self._bsm_left, self._bsm_right)

  def draw(self, rect: rl.Rectangle, left: bool, right: bool, brake: float, lat_only: bool = False,
           bsm_left: bool = False, bsm_right: bool = False) -> None:
    """Drawing only, so a preview harness can drive it without a running SubMaster.

    Advances the fade filters, so call it exactly once per frame.
    """
    left_alpha = self._left_filter.update(1.0 if left else 0.0)
    right_alpha = self._right_filter.update(1.0 if right else 0.0)
    brake_level = self._brake_filter.update(brake if brake > BRAKE_DEADZONE else 0.0)
    lat_only_alpha = self._lat_only_filter.update(1.0 if lat_only else 0.0)
    bsm_left_alpha = self._bsm_left_filter.update(1.0 if bsm_left else 0.0)
    bsm_right_alpha = self._bsm_right_filter.update(1.0 if bsm_right else 0.0)

    center_x = rect.x + rect.width / 2
    arrow_y = CONFIG.arrow_center_y - CONFIG.arrow_height / 2

    # tint the arrow when that side's blind spot is occupied, which is also the reason an
    # automatic lane change is sitting there not starting
    if left_alpha > MIN_VISIBLE_ALPHA:
      pos = rl.Vector2(center_x - CONFIG.arrow_gap - CONFIG.arrow_width, arrow_y)
      rl.draw_texture_ex(self._txt_left, pos, 0.0, 1.0, self._arrow_tint(left_alpha, bsm_left))

    if right_alpha > MIN_VISIBLE_ALPHA:
      pos = rl.Vector2(center_x + CONFIG.arrow_gap, arrow_y)
      rl.draw_texture_ex(self._txt_right, pos, 0.0, 1.0, self._arrow_tint(right_alpha, bsm_right))

    bsm_y = rect.y + (rect.height - CONFIG.bsm_height) / 2
    if bsm_left_alpha > MIN_VISIBLE_ALPHA:
      self._draw_bsm_bar(rect.x + CONFIG.bsm_inset, bsm_y, bsm_left_alpha)

    if bsm_right_alpha > MIN_VISIBLE_ALPHA:
      x = rect.x + rect.width - CONFIG.bsm_inset - CONFIG.bsm_width
      self._draw_bsm_bar(x, bsm_y, bsm_right_alpha)

    if brake_level > MIN_VISIBLE_ALPHA:
      track = rl.Rectangle(center_x - CONFIG.brake_width / 2, CONFIG.brake_y, CONFIG.brake_width, CONFIG.brake_height)
      rl.draw_rectangle_rounded(track, CONFIG.brake_roundness, CONFIG.brake_segments, COLORS.TRACK)

      # keep the fill at least as wide as it is tall, otherwise the rounded ends degenerate
      fill_width = max(CONFIG.brake_height, track.width * min(1.0, brake_level))
      fill = rl.Rectangle(track.x, track.y, fill_width, track.height)
      rl.draw_rectangle_rounded(fill, CONFIG.brake_roundness, CONFIG.brake_segments, COLORS.BRAKE)

    if lat_only_alpha > MIN_VISIBLE_ALPHA:
      self._draw_lat_only_badge(rect, lat_only_alpha)

  @staticmethod
  def _arrow_tint(alpha: float, blindspot: bool) -> rl.Color:
    c = COLORS.BSM if blindspot else rl.Color(255, 255, 255, 255)
    return rl.Color(c.r, c.g, c.b, int(255 * alpha))

  @staticmethod
  def _draw_bsm_bar(x: float, y: float, alpha: float) -> None:
    bar = rl.Rectangle(x, y, CONFIG.bsm_width, CONFIG.bsm_height)
    color = rl.Color(COLORS.BSM.r, COLORS.BSM.g, COLORS.BSM.b, int(255 * alpha))
    rl.draw_rectangle_rounded(bar, CONFIG.bsm_roundness, CONFIG.bsm_segments, color)

  def _draw_lat_only_badge(self, rect: rl.Rectangle, alpha: float) -> None:
    """A badge under the set speed box saying openpilot is steering and nothing else."""
    width = CONFIG.set_speed_width_metric if ui_state.is_metric else CONFIG.set_speed_width_imperial
    x = rect.x + CONFIG.set_speed_x + (CONFIG.set_speed_width_imperial - width) // 2
    y = rect.y + CONFIG.set_speed_y + CONFIG.set_speed_height + CONFIG.lat_only_gap

    a = int(255 * alpha)
    badge = rl.Rectangle(x, y, width, CONFIG.lat_only_height)
    rl.draw_rectangle_rounded(badge, 0.35, 10, rl.Color(COLORS.LAT_ONLY_BG.r, COLORS.LAT_ONLY_BG.g,
                                                        COLORS.LAT_ONLY_BG.b, int(COLORS.LAT_ONLY_BG.a * alpha)))
    rl.draw_rectangle_rounded_lines_ex(badge, 0.35, 10, 6, rl.Color(COLORS.LAT_ONLY.r, COLORS.LAT_ONLY.g,
                                                                    COLORS.LAT_ONLY.b, a))

    text_color = rl.Color(COLORS.LAT_ONLY.r, COLORS.LAT_ONLY.g, COLORS.LAT_ONLY.b, a)
    lines = (tr("STEERING"), tr("ONLY"))
    line_height = CONFIG.lat_only_font + 6
    top = y + (CONFIG.lat_only_height - line_height * len(lines)) / 2

    for i, line in enumerate(lines):
      text_width = measure_text_cached(self._font_semi_bold, line, CONFIG.lat_only_font).x
      pos = rl.Vector2(x + (width - text_width) / 2, top + i * line_height)
      rl.draw_text_ex(self._font_semi_bold, line, pos, CONFIG.lat_only_font, 0, text_color)
