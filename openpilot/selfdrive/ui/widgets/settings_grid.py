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

SEG_WIDTH = 108
SEG_GAP = 10
SEG_HEIGHT = 62

# Toggle draws itself at a fixed size, these have to match
TOGGLE_WIDTH = 160
TOGGLE_HEIGHT = 80

LABEL_FONT_SIZE = 36
SEG_FONT_SIZE = 30

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
CHOICE_SETTINGS = (
  ("AutoLaneChangeTimer", "Auto lane change", AUTO_LANE_CHANGE_TIMERS, ("Nudge", "1s", "2s", "3s")),
  ("BlinkerPauseSpeed", "Blinker pause", BLINKER_PAUSE_SPEEDS_MPH, ("Off", "20", "40", "Any")),
  ("BlinkerPauseDelay", "Resume delay", BLINKER_PAUSE_DELAYS, ("Now", "1s", "2s", "3s")),
  ("CurveAdvisory", "Curve warning", CURVE_ADVISORY_LEVELS, ("Off", "Late", "Norm", "Early")),
  ("LanePosition", "Lane position", LANE_POSITION_OFFSETS_CM, ("FL", "L", "C", "R", "FR")),
  ("BrightnessLevel", "Brightness", BRIGHTNESS_LEVELS, ("Auto", "25", "50", "75", "100")),
)

# what changes how the car drives. this is the set worth having on the home screen, where the
# question is what to try on the next drive rather than what to change during one
DRIVING_PARAMS = tuple(s[0] for s in CHOICE_SETTINGS) + ("MadsEnabled", "MadsMainSwitch", "ReverseGearDebounce")

# and what only changes how the screen looks
DISPLAY_PARAMS = tuple(s[0] for s in BOOL_SETTINGS if s[0] not in DRIVING_PARAMS)

ALL_PARAMS = DRIVING_PARAMS + DISPLAY_PARAMS


class Segmented(Widget):
  """A row of buttons where exactly one is selected, sized to fit beside a label."""

  def __init__(self, texts: tuple[str, ...], selected: int, callback: Callable[[int], None]):
    super().__init__()
    self._texts = texts
    self._selected = selected
    self._callback = callback
    self._font = gui_app.font(FontWeight.MEDIUM)

  @staticmethod
  def width_for(count: int) -> int:
    return count * SEG_WIDTH + (count - 1) * SEG_GAP

  @property
  def selected(self) -> int:
    return self._selected

  def set_selected(self, index: int) -> None:
    self._selected = index

  def _button_rect(self, index: int) -> rl.Rectangle:
    y = self._rect.y + (self._rect.height - SEG_HEIGHT) / 2
    return rl.Rectangle(self._rect.x + index * (SEG_WIDTH + SEG_GAP), y, SEG_WIDTH, SEG_HEIGHT)

  def _render(self, _: rl.Rectangle) -> None:
    mouse_pos = rl.get_mouse_position()
    for i, text in enumerate(self._texts):
      button_rect = self._button_rect(i)
      if i == self._selected:
        color = SEG_SELECTED
      elif self.enabled and self.is_pressed and rl.check_collision_point_rec(mouse_pos, button_rect):
        color = SEG_PRESSED
      else:
        color = SEG_BG
      if not self.enabled:
        color = rl.Color(color.r, color.g, color.b, 110)

      rl.draw_rectangle_rounded(button_rect, 1.0, 20, color)

      text_size = measure_text_cached(self._font, text, SEG_FONT_SIZE)
      text_pos = rl.Vector2(button_rect.x + (SEG_WIDTH - text_size.x) / 2, button_rect.y + (SEG_HEIGHT - text_size.y) / 2)
      rl.draw_text_ex(self._font, text, text_pos, SEG_FONT_SIZE, 0, SEG_TEXT if self.enabled else SEG_TEXT_DISABLED)

  def _handle_mouse_release(self, mouse_pos: MousePos) -> None:
    for i in range(len(self._texts)):
      if rl.check_collision_point_rec(mouse_pos, self._button_rect(i)):
        self._selected = i
        self._callback(i)
        return


class SettingsGrid(Widget):
  """Label on the left, control on the right, filled column by column."""

  def __init__(self, param_names: tuple[str, ...], rows_per_column: int, row_height: int = ROW_HEIGHT):
    super().__init__()
    self._params = Params()
    self._param_names = param_names
    self._rows_per_column = rows_per_column
    self._row_height = row_height
    self._columns = math.ceil(len(param_names) / rows_per_column)
    self._font = gui_app.font(FontWeight.MEDIUM)

    self._labels = {s[0]: s[1] for s in BOOL_SETTINGS} | {s[0]: s[1] for s in CHOICE_SETTINGS}
    self._restarts = {s[0] for s in BOOL_SETTINGS if s[2]} & set(param_names)
    self._choice_values = {s[0]: s[2] for s in CHOICE_SETTINGS if s[0] in param_names}

    self._toggles: dict[str, Toggle] = {}
    for param, _, _ in BOOL_SETTINGS:
      if param in param_names:
        self._toggles[param] = Toggle(initial_state=self._params.get_bool(param),
                                      callback=lambda state, p=param: self._set_bool(p, state))

    self._segments: dict[str, Segmented] = {}
    for param, _, _, texts in CHOICE_SETTINGS:
      if param in param_names:
        self._segments[param] = Segmented(texts, self._selected_index(param),
                                          lambda index, p=param: self._set_choice(p, index))

    self._controls: dict[str, Widget] = {**self._toggles, **self._segments}

  @property
  def columns(self) -> int:
    return self._columns

  def height_hint(self) -> float:
    return min(len(self._param_names), self._rows_per_column) * self._row_height

  def column_width(self, total_width: float) -> float:
    return (total_width - (self._columns - 1) * COLUMN_GAP) / self._columns

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

    for i, param in enumerate(self._param_names):
      control = self._controls[param]
      x = rect.x + (i // self._rows_per_column) * (column_width + COLUMN_GAP)
      y = rect.y + (i % self._rows_per_column) * self._row_height

      is_toggle = isinstance(control, Toggle)
      control_width = TOGGLE_WIDTH if is_toggle else Segmented.width_for(len(self._choice_values[param]))

      label_color = LABEL_COLOR if control.enabled else LABEL_DISABLED_COLOR
      label_size = measure_text_cached(self._font, self._labels[param], LABEL_FONT_SIZE)
      rl.draw_text_ex(self._font, self._labels[param],
                      rl.Vector2(x, y + (self._row_height - label_size.y) / 2), LABEL_FONT_SIZE, 0, label_color)

      # Toggle forces its own 160x80 size, so it only reads the top left corner
      control_height = TOGGLE_HEIGHT if is_toggle else self._row_height
      control.render(rl.Rectangle(x + column_width - control_width,
                                  y + (self._row_height - control_height) / 2,
                                  control_width, control_height))
