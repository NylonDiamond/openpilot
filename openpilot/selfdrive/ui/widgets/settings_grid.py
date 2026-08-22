"""A compact grid of the fork's settings, laid out in columns.

The settings menu is the place to read about a setting. This is the place to change one you
already understand, either parked on the home screen or over the camera while driving, so a
change can be judged against the road that raised the question. Labels are terse and
untranslated for the same reason: they are reminders, not explanations.
"""

import math
from collections.abc import Callable

import pyray as rl

from openpilot.common.params import Params
from openpilot.selfdrive.controls.lib.blinker_pause import ANY_SPEED_MPH, BLINKER_PAUSE_SPEEDS_MPH
from openpilot.selfdrive.controls.lib.lane_position import LANE_POSITION_OFFSETS_CM
from openpilot.selfdrive.ui.layouts.settings.toggles import AUTO_LANE_CHANGE_TIMERS, BLINKER_PAUSE_DELAYS, CURVE_ADVISORY_LEVELS
from openpilot.selfdrive.ui.ui_state import BRIGHTNESS_LEVELS, device, ui_state
from openpilot.system.ui.lib.application import FontWeight, MousePos, gui_app
from openpilot.system.ui.lib.text_measure import measure_text_cached
from openpilot.system.ui.widgets import Widget
from openpilot.system.ui.widgets.toggle import Toggle

ROW_HEIGHT = 92
COLUMN_GAP = 60

# the pills stretch into whatever the column has spare, between a size that still reads at a
# glance and a size past which they are just wide. the onroad panel is two columns over the
# camera and lands near the bottom of that range, the home screen has a full page to itself and
# raises the ceiling to fill it
SEG_MIN_WIDTH = 96
SEG_MAX_WIDTH = 200
SEG_GAP = 15
SEG_HEIGHT = 78
# the least a label may sit from the control beside it
LABEL_GAP = 40
# what separates two switches sharing a row. wide enough that a near miss on one cannot land in
# the next one's tap band
INLINE_GAP = 60

# Toggle draws itself at a fixed size, these have to match
TOGGLE_WIDTH = 160
TOGGLE_HEIGHT = 80
# ...and 160 x 80 is a small target to hit in a moving car, so the switch takes taps from a band
# of the row that starts at the switch and runs on past it. it never reaches back to the label,
# so a tap that missed the row entirely does not read as a deliberate one
TOGGLE_HIT_WIDTH = 320

LABEL_FONT_SIZE = 38
SEG_FONT_SIZE = 32

LABEL_COLOR = rl.Color(228, 228, 228, 255)
LABEL_DISABLED_COLOR = rl.Color(120, 120, 120, 255)
SEG_SELECTED = rl.Color(51, 171, 76, 255)
SEG_PRESSED = rl.Color(90, 90, 90, 255)
SEG_BG = rl.Color(57, 57, 57, 255)
SEG_TEXT = rl.Color(228, 228, 228, 255)
SEG_TEXT_DISABLED = rl.Color(130, 130, 130, 255)

# param, label, restarts openpilot when changed
BOOL_SETTINGS = (
  ("MadsEnabled", "MADS", True),
  ("MadsMainSwitch", "MADS main switch", True),
  ("SubaruAutoResume", "Auto resume", True),
  ("ReverseGearDebounce", "Reverse debounce", False),
  ("IsLdwEnabled", "Lane departure warn", False),
  ("ShowLeadIndicator", "Lead marker", False),
  ("EngagementPathColor", "Path color by steer", False),
  ("HideExperimentalButton", "Hide exp button", False),
  ("WideCameraLowSpeed", "Wide cam low speed", False),
  ("AlwaysOnDM", "Always-on DM", False),
  ("DisengageOnAccelerator", "Disengage on gas", False),
  ("IsMetric", "Metric", False),
)

# param, label, stored values, button labels
# brightness leads: it is the one here that is worth changing without any thought about the
# drive, and the top row is the easiest to hit both parked and over the camera
CHOICE_SETTINGS = (
  ("BrightnessLevel", "Brightness", BRIGHTNESS_LEVELS, ("Auto", "25", "50", "75", "100")),
  ("AutoLaneChangeTimer", "Auto lane change", AUTO_LANE_CHANGE_TIMERS, ("Nudge", "1s", "2s", "3s")),
  ("BlinkerPauseSpeed", "Blinker pause", BLINKER_PAUSE_SPEEDS_MPH, ("Off", "20", "40", "Any")),
  ("BlinkerPauseDelay", "Resume delay", BLINKER_PAUSE_DELAYS, ("Now", "1s", "2s", "3s")),
  ("CurveAdvisory", "Curve warning", CURVE_ADVISORY_LEVELS, ("Off", "Late", "Norm", "Early")),
  ("LanePosition", "Lane position", LANE_POSITION_OFFSETS_CM, ("FL", "L", "C", "R", "FR")),
)

# what changes how the car drives. this is the set worth having on the home screen, where the
# question is what to try on the next drive rather than what to change during one
DRIVING_PARAMS = tuple(s[0] for s in CHOICE_SETTINGS) + ("MadsEnabled", "MadsMainSwitch", "SubaruAutoResume", "ReverseGearDebounce")

# and what only changes how the screen looks
DISPLAY_PARAMS = tuple(s[0] for s in BOOL_SETTINGS if s[0] not in DRIVING_PARAMS)

ALL_PARAMS = DRIVING_PARAMS + DISPLAY_PARAMS


class RowToggle(Toggle):
  """A Toggle that draws at its fixed size but answers to the whole band it is given.

  Toggle pins its own rect to 160 x 80, which is both what it draws and what it accepts taps
  in. Keeping the band as the widget rect and moving the fixed rect back only for the draw
  leaves the switch looking the same while making it much harder to miss.
  """

  def set_rect(self, rect: rl.Rectangle) -> None:
    Widget.set_rect(self, rect)

  def _render(self, _: rl.Rectangle) -> None:
    band = self._rect
    self._rect = rl.Rectangle(band.x, band.y + (band.height - TOGGLE_HEIGHT) / 2, TOGGLE_WIDTH, TOGGLE_HEIGHT)
    try:
      return super()._render(self._rect)
    finally:
      self._rect = band


class Segmented(Widget):
  """A row of buttons where exactly one is selected, sized to fit beside a label."""

  def __init__(self, texts: tuple[str, ...], selected: int, callback: Callable[[int], None]):
    super().__init__()
    self._texts = texts
    self._selected = selected
    self._callback = callback
    self._font = gui_app.font(FontWeight.MEDIUM)
    self._button_width = SEG_MAX_WIDTH

  def set_button_width(self, width: int) -> None:
    self._button_width = width

  @property
  def width(self) -> int:
    return len(self._texts) * self._button_width + (len(self._texts) - 1) * SEG_GAP

  @property
  def selected(self) -> int:
    return self._selected

  def set_selected(self, index: int) -> None:
    self._selected = index

  def _button_rect(self, index: int) -> rl.Rectangle:
    y = self._rect.y + (self._rect.height - SEG_HEIGHT) / 2
    return rl.Rectangle(self._rect.x + index * (self._button_width + SEG_GAP), y, self._button_width, SEG_HEIGHT)

  def _touch_rect(self, index: int) -> rl.Rectangle:
    """The pill is what you aim at, but the whole row band around it is what you can hit.

    Nothing else lives in the gaps between the pills or above and below them, so a near miss is
    unambiguous and there is no reason to make it cost a second tap.
    """
    button_rect = self._button_rect(index)
    return rl.Rectangle(button_rect.x - SEG_GAP / 2, self._rect.y,
                        self._button_width + SEG_GAP, self._rect.height)

  def _render(self, _: rl.Rectangle) -> None:
    mouse_pos = rl.get_mouse_position()
    for i, text in enumerate(self._texts):
      button_rect = self._button_rect(i)
      if i == self._selected:
        color = SEG_SELECTED
      elif self.enabled and self.is_pressed and rl.check_collision_point_rec(mouse_pos, self._touch_rect(i)):
        color = SEG_PRESSED
      else:
        color = SEG_BG
      if not self.enabled:
        color = rl.Color(color.r, color.g, color.b, 110)

      rl.draw_rectangle_rounded(button_rect, 1.0, 20, color)

      text_size = measure_text_cached(self._font, text, SEG_FONT_SIZE)
      text_pos = rl.Vector2(button_rect.x + (self._button_width - text_size.x) / 2,
                            button_rect.y + (SEG_HEIGHT - text_size.y) / 2)
      rl.draw_text_ex(self._font, text, text_pos, SEG_FONT_SIZE, 0, SEG_TEXT if self.enabled else SEG_TEXT_DISABLED)

  def _handle_mouse_release(self, mouse_pos: MousePos) -> None:
    for i in range(len(self._texts)):
      if rl.check_collision_point_rec(mouse_pos, self._touch_rect(i)):
        self._selected = i
        self._callback(i)
        return


class SettingsGrid(Widget):
  """Label on the left, control on the right, filled column by column."""

  def __init__(self, param_names: tuple[str, ...], rows_per_column: int, row_height: int = ROW_HEIGHT,
               inline_tail: int = 0, max_button_width: int = SEG_MAX_WIDTH):
    super().__init__()
    self._params = Params()
    self._param_names = param_names
    self._rows_per_column = rows_per_column
    self._row_height = row_height
    self._max_button_width = max_button_width
    self._font = gui_app.font(FontWeight.MEDIUM)

    # the last few settings can share a single row instead of taking one each. switches are the
    # only control narrow enough for that, and reading three of them as one group costs nothing
    self._inline_tail = inline_tail
    self._stacked_params = param_names[:len(param_names) - inline_tail]
    self._inline_params = param_names[len(param_names) - inline_tail:]
    self._slots = len(self._stacked_params) + (1 if inline_tail else 0)
    self._columns = math.ceil(self._slots / rows_per_column)

    self._labels = {s[0]: s[1] for s in BOOL_SETTINGS} | {s[0]: s[1] for s in CHOICE_SETTINGS}
    self._restarts = {s[0] for s in BOOL_SETTINGS if s[2]} & set(param_names)
    self._choice_values = {s[0]: s[2] for s in CHOICE_SETTINGS if s[0] in param_names}

    self._toggles: dict[str, RowToggle] = {}
    for param, _, _ in BOOL_SETTINGS:
      if param in param_names:
        self._toggles[param] = RowToggle(initial_state=self._params.get_bool(param),
                                         callback=lambda state, p=param: self._set_bool(p, state))

    self._segments: dict[str, Segmented] = {}
    for param, _, _, texts in CHOICE_SETTINGS:
      if param in param_names:
        self._segments[param] = Segmented(texts, self._selected_index(param),
                                          lambda index, p=param: self._set_choice(p, index))

    self._controls: dict[str, Widget] = {**self._toggles, **self._segments}

    assert all(p in self._toggles for p in self._inline_params), "only switches fit on a shared row"

    # what has to fit beside the pills, so they can be sized to the column at render time
    self._widest_choice_label = max((measure_text_cached(self._font, self._labels[p], LABEL_FONT_SIZE).x
                                     for p in self._segments), default=0.0)
    self._widest_label = max((measure_text_cached(self._font, self._labels[p], LABEL_FONT_SIZE).x
                              for p in self._stacked_params), default=0.0)
    # one width for every cell of the shared row, so those switches line up with each other
    self._widest_inline_label = max((measure_text_cached(self._font, self._labels[p], LABEL_FONT_SIZE).x
                                     for p in self._inline_params), default=0.0)
    self._most_choices = max((len(v) for v in self._choice_values.values()), default=0)

  @property
  def columns(self) -> int:
    return self._columns

  def height_hint(self) -> float:
    return min(self._slots, self._rows_per_column) * self._row_height

  def column_width(self, total_width: float) -> float:
    return (total_width - (self._columns - 1) * COLUMN_GAP) / self._columns

  def _button_width(self, column_width: float) -> int:
    """Spend whatever the widest choice row does not need on the buttons themselves."""
    if not self._most_choices:
      return self._max_button_width
    spare = column_width - self._widest_choice_label - LABEL_GAP - (self._most_choices - 1) * SEG_GAP
    return int(min(self._max_button_width, max(SEG_MIN_WIDTH, spare / self._most_choices)))

  def show_event(self) -> None:
    super().show_event()
    self.refresh()

  def refresh(self) -> None:
    """Pull every control back from params, so the grid never shows a stale value."""
    for param, toggle in self._toggles.items():
      toggle.set_state(self._params.get_bool(param))
    for param, segment in self._segments.items():
      segment.set_selected(self._selected_index(param))

  def _selected_index(self, param: str) -> int:
    values = self._choice_values[param]
    value = self._params.get(param, return_default=True)
    return values.index(value) if value in values else 0

  def _set_bool(self, param: str, state: bool) -> None:
    self._params.put_bool(param, state, block=True)
    if param in self._restarts:
      self._params.put_bool("OnroadCycleRequested", True, block=True)

  def _set_choice(self, param: str, index: int) -> None:
    value = self._choice_values[param][index]
    self._params.put(param, value, block=True)
    if param == "BrightnessLevel":
      device.set_brightness_level(value)

  def _update_state(self) -> None:
    # mirrors the settings page: these can only be applied at car init, so block them while engaged
    for param in self._restarts:
      self._toggles[param].set_enabled(not ui_state.engaged)

    # the delay says nothing with the pause off, and a pause at any speed swallows every signal
    # before the lane change assist can see one. read the control rather than the param, so this
    # costs nothing per frame
    if "BlinkerPauseSpeed" in self._segments:
      pause_speed = BLINKER_PAUSE_SPEEDS_MPH[self._segments["BlinkerPauseSpeed"].selected]
      if "BlinkerPauseDelay" in self._segments:
        self._segments["BlinkerPauseDelay"].set_enabled(pause_speed > 0)
      if "AutoLaneChangeTimer" in self._segments:
        self._segments["AutoLaneChangeTimer"].set_enabled(pause_speed < ANY_SPEED_MPH)

  def _render(self, rect: rl.Rectangle) -> None:
    column_width = self.column_width(rect.width)

    # one width for every row, so the pills line up down the column
    button_width = self._button_width(column_width)
    for segment in self._segments.values():
      segment.set_button_width(button_width)

    for i, param in enumerate(self._stacked_params):
      control = self._controls[param]
      x, y = self._slot_origin(rect, i, column_width)

      is_toggle = isinstance(control, RowToggle)
      control_width = TOGGLE_HIT_WIDTH if is_toggle else control.width

      self._draw_label(param, x, y, control.enabled)

      # the controls sit just past the longest label rather than out at the column edge: the
      # driver sits to the left of this screen, so the far right is the worst place to reach.
      # a column with no slack clamps back to the edge.
      control_x = min(x + self._widest_label + LABEL_GAP, x + column_width - control_width)

      # both controls take the whole row band, and place their own smaller visuals inside it
      control.render(rl.Rectangle(control_x, y, control_width, self._row_height))

    if self._inline_params:
      self._render_inline_row(rect, column_width)

  def _slot_origin(self, rect: rl.Rectangle, slot: int, column_width: float) -> tuple[float, float]:
    return (rect.x + (slot // self._rows_per_column) * (column_width + COLUMN_GAP),
            rect.y + (slot % self._rows_per_column) * self._row_height)

  def _draw_label(self, param: str, x: float, y: float, enabled: bool) -> None:
    label_size = measure_text_cached(self._font, self._labels[param], LABEL_FONT_SIZE)
    rl.draw_text_ex(self._font, self._labels[param], rl.Vector2(x, y + (self._row_height - label_size.y) / 2),
                    LABEL_FONT_SIZE, 0, LABEL_COLOR if enabled else LABEL_DISABLED_COLOR)

  def _render_inline_row(self, rect: rl.Rectangle, column_width: float) -> None:
    """The tail of the grid, laid out across one row instead of down several."""
    x, y = self._slot_origin(rect, len(self._stacked_params), column_width)
    cell_width = (column_width - (len(self._inline_params) - 1) * INLINE_GAP) / len(self._inline_params)

    for i, param in enumerate(self._inline_params):
      control = self._controls[param]
      cell_x = x + i * (cell_width + INLINE_GAP)
      self._draw_label(param, cell_x, y, control.enabled)

      # same rule as a full row: the band starts at the switch and runs to the end of the cell,
      # never back to a label and never into the cell beside it
      control_x = cell_x + self._widest_inline_label + LABEL_GAP
      control.render(rl.Rectangle(control_x, y, max(TOGGLE_WIDTH, cell_x + cell_width - control_x), self._row_height))
