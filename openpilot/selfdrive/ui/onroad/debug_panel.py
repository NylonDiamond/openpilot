"""On-screen settings panel for the driving view.

Every setting here already exists in the settings menu. The point is reaching them without
leaving the road view, so a change can be made and judged on the same piece of road instead of
three taps and a scroll away. Labels are deliberately terse and untranslated: this is a bench
tool for testing the fork, not part of the shipped UI.
"""

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

# geometry. the row count drives the panel height, so adding a setting below is the only edit needed
ROWS_PER_COLUMN = 9
ROW_HEIGHT = 92
HEADER_HEIGHT = 66
PANEL_PADDING = 28
PANEL_INSET = 30
COLUMN_GAP = 60

SEG_WIDTH = 108
SEG_GAP = 10
SEG_HEIGHT = 62

# Toggle draws itself at a fixed size, these have to match
TOGGLE_WIDTH = 160
TOGGLE_HEIGHT = 80

BUTTON_RADIUS = 46

LABEL_FONT_SIZE = 36
SEG_FONT_SIZE = 30
HEADER_FONT_SIZE = 44

PANEL_BG = rl.Color(18, 18, 20, 242)
PANEL_BORDER = rl.Color(255, 255, 255, 60)
SCRIM = rl.Color(0, 0, 0, 140)
LABEL_COLOR = rl.Color(228, 228, 228, 255)
LABEL_DISABLED_COLOR = rl.Color(120, 120, 120, 255)
HEADER_COLOR = rl.Color(255, 255, 255, 255)
HINT_COLOR = rl.Color(140, 140, 140, 255)
SEG_SELECTED = rl.Color(51, 171, 76, 255)
SEG_PRESSED = rl.Color(90, 90, 90, 255)
SEG_BG = rl.Color(57, 57, 57, 255)
SEG_TEXT = rl.Color(228, 228, 228, 255)
SEG_TEXT_DISABLED = rl.Color(130, 130, 130, 255)
BUTTON_BG = rl.Color(0, 0, 0, 166)
BUTTON_GLYPH = rl.Color(255, 255, 255, 255)

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

# left column carries what changes how the car drives, right column what changes how it looks.
# the ninth right hand slot is left empty for the floating button to sit in
LEFT_PARAMS = tuple(s[0] for s in CHOICE_SETTINGS) + ("MadsEnabled", "MadsMainSwitch", "ReverseGearDebounce")


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


class DebugButton(Widget):
  """The floating handle that opens and closes the panel."""

  def __init__(self, on_click: Callable[[], None]):
    super().__init__()
    self._on_click = on_click
    self._open = False

  def set_open(self, is_open: bool) -> None:
    self._open = is_open

  def _render(self, _: rl.Rectangle) -> None:
    cx = int(self._rect.x + self._rect.width / 2)
    cy = int(self._rect.y + self._rect.height / 2)
    rl.draw_circle(cx, cy, BUTTON_RADIUS, BUTTON_BG)
    rl.draw_circle_lines(cx, cy, BUTTON_RADIUS, PANEL_BORDER)

    glyph = rl.Color(BUTTON_GLYPH.r, BUTTON_GLYPH.g, BUTTON_GLYPH.b, 180 if self.is_pressed else 255)
    if self._open:
      # a cross, so an open panel offers an obvious way back out
      for dx, dy in ((-1, -1), (-1, 1)):
        rl.draw_line_ex(rl.Vector2(cx + dx * 16, cy + dy * 16), rl.Vector2(cx - dx * 16, cy - dy * 16), 5, glyph)
    else:
      # three sliders, the usual shorthand for settings
      for i, knob_dx in enumerate((-8, 10, -2)):
        y = cy - 16 + i * 16
        rl.draw_line_ex(rl.Vector2(cx - 24, y), rl.Vector2(cx + 24, y), 4, glyph)
        rl.draw_circle(cx + knob_dx, y, 7, glyph)

  def _handle_mouse_release(self, _: MousePos) -> None:
    self._on_click()


class DebugPanel(Widget):
  """A button on the driving view that opens an overlay of the fork's settings."""

  def __init__(self):
    super().__init__()
    self._params = Params()
    self._open = False
    # a press the panel handled itself, so the road view does not also treat it as a tap
    self._consumed_press = False

    self._font_medium = gui_app.font(FontWeight.MEDIUM)
    self._font_bold = gui_app.font(FontWeight.BOLD)

    self._panel_rect = rl.Rectangle(0, 0, 0, 0)
    self._button = DebugButton(self._toggle_open)
    self._labels: dict[str, str] = {}
    self._restarts: set[str] = set()
    self._toggles: dict[str, Toggle] = {}
    self._segments: dict[str, Segmented] = {}
    self._choice_values: dict[str, tuple] = {}

    for param, label, restarts in BOOL_SETTINGS:
      self._labels[param] = label
      if restarts:
        self._restarts.add(param)
      self._toggles[param] = Toggle(
        initial_state=self._params.get_bool(param),
        callback=lambda state, p=param: self._set_bool(p, state),
      )

    for param, label, values, texts in CHOICE_SETTINGS:
      self._labels[param] = label
      self._choice_values[param] = values
      self._segments[param] = Segmented(texts, self._selected_index(param), lambda index, p=param: self._set_choice(p, index))

    self._controls: dict[str, Widget] = {**self._toggles, **self._segments}
    self._left_params = list(LEFT_PARAMS)
    self._right_params = [p for p in self._labels if p not in LEFT_PARAMS]

    assert len(self._left_params) <= ROWS_PER_COLUMN, "left column overflows the panel"
    assert len(self._right_params) < ROWS_PER_COLUMN, "right column must leave its last row for the button"

  @property
  def is_open(self) -> bool:
    return self._open

  def user_interacting(self) -> bool:
    """True when the road view should ignore the current touch."""
    if not ui_state.show_debug_panel:
      return False
    return self._open or self._consumed_press or self._button.is_pressed

  def _selected_index(self, param: str) -> int:
    values = self._choice_values[param]
    value = self._params.get(param, return_default=True)
    return values.index(value) if value in values else 0

  def _toggle_open(self) -> None:
    self._open = not self._open
    if self._open:
      self._refresh()

  def _refresh(self) -> None:
    """Pull every control back from params, so the panel never shows a stale value."""
    for param, toggle in self._toggles.items():
      toggle.set_state(self._params.get_bool(param))
    for param, segment in self._segments.items():
      segment.set_selected(self._selected_index(param))

  def _set_bool(self, param: str, state: bool) -> None:
    self._params.put_bool(param, state, block=True)
    if param in self._restarts:
      self._params.put_bool("OnroadCycleRequested", True, block=True)

  def _set_choice(self, param: str, index: int) -> None:
    value = self._choice_values[param][index]
    self._params.put(param, value, block=True)
    if param == "BrightnessLevel":
      device.set_brightness_level(value)

  def _update_layout_rects(self) -> None:
    height = ROWS_PER_COLUMN * ROW_HEIGHT + HEADER_HEIGHT + 2 * PANEL_PADDING
    width = self._rect.width - 2 * PANEL_INSET
    self._panel_rect = rl.Rectangle(
      self._rect.x + PANEL_INSET,
      self._rect.y + (self._rect.height - height) / 2,
      width,
      height,
    )

    # the button parks in the empty last slot of the right column, so it never moves when the
    # panel opens and a second tap in the same place closes it again
    row_center_y = (self._panel_rect.y + PANEL_PADDING + HEADER_HEIGHT +
                    (ROWS_PER_COLUMN - 1) * ROW_HEIGHT + ROW_HEIGHT / 2)
    self._button.set_rect(rl.Rectangle(
      self._panel_rect.x + self._panel_rect.width - PANEL_PADDING - 2 * BUTTON_RADIUS,
      row_center_y - BUTTON_RADIUS,
      2 * BUTTON_RADIUS,
      2 * BUTTON_RADIUS,
    ))

  def _update_state(self) -> None:
    # turning the toggle off mid-drive has to close the panel too, or it stays on screen with
    # nothing left to dismiss it
    if not ui_state.show_debug_panel:
      self._open = False

    self._button.set_open(self._open)
    if not self._open:
      return

    # mirrors the settings page: these can only be applied at car init, so block them while engaged
    for param in self._restarts:
      self._toggles[param].set_enabled(not ui_state.engaged)

    # the delay says nothing with the pause off, and a pause at any speed swallows every signal
    # before the lane change assist can see one. read the control rather than the param, so this
    # costs nothing per frame
    pause_speed = BLINKER_PAUSE_SPEEDS_MPH[self._segments["BlinkerPauseSpeed"].selected]
    self._segments["BlinkerPauseDelay"].set_enabled(pause_speed > 0)
    self._segments["AutoLaneChangeTimer"].set_enabled(pause_speed < ANY_SPEED_MPH)

  def _render(self, rect: rl.Rectangle) -> None:
    self._consumed_press = False
    if not ui_state.show_debug_panel:
      return

    if self._open:
      rl.draw_rectangle_rec(rect, SCRIM)
      rl.draw_rectangle_rounded(self._panel_rect, 0.03, 20, PANEL_BG)
      rl.draw_rectangle_rounded_lines_ex(self._panel_rect, 0.03, 20, 2, PANEL_BORDER)
      self._draw_header()
      self._draw_column(self._left_params, 0)
      self._draw_column(self._right_params, 1)

    self._button.render()

  def _draw_header(self) -> None:
    x = self._panel_rect.x + PANEL_PADDING
    y = self._panel_rect.y + PANEL_PADDING
    rl.draw_text_ex(self._font_bold, "DEBUG", rl.Vector2(x, y), HEADER_FONT_SIZE, 0, HEADER_COLOR)

    hint = "changes apply live, MADS needs a restart"
    hint_width = measure_text_cached(self._font_medium, hint, SEG_FONT_SIZE).x
    hint_x = self._panel_rect.x + self._panel_rect.width - PANEL_PADDING - hint_width
    rl.draw_text_ex(self._font_medium, hint, rl.Vector2(hint_x, y + 12), SEG_FONT_SIZE, 0, HINT_COLOR)

  def _draw_column(self, params: list[str], column: int) -> None:
    column_width = (self._panel_rect.width - 2 * PANEL_PADDING - COLUMN_GAP) / 2
    x = self._panel_rect.x + PANEL_PADDING + column * (column_width + COLUMN_GAP)
    top = self._panel_rect.y + PANEL_PADDING + HEADER_HEIGHT

    for row, param in enumerate(params):
      control = self._controls[param]
      y = top + row * ROW_HEIGHT
      is_toggle = isinstance(control, Toggle)
      control_width = TOGGLE_WIDTH if is_toggle else Segmented.width_for(len(self._choice_values[param]))
      control_x = x + column_width - control_width

      label_color = LABEL_COLOR if control.enabled else LABEL_DISABLED_COLOR
      label_size = measure_text_cached(self._font_medium, self._labels[param], LABEL_FONT_SIZE)
      rl.draw_text_ex(self._font_medium, self._labels[param],
                      rl.Vector2(x, y + (ROW_HEIGHT - label_size.y) / 2), LABEL_FONT_SIZE, 0, label_color)

      # Toggle forces its own 160x80 size, so it only reads the top left corner
      control_height = TOGGLE_HEIGHT if is_toggle else ROW_HEIGHT
      control_y = y + (ROW_HEIGHT - control_height) / 2
      control.render(rl.Rectangle(control_x, control_y, control_width, control_height))

  def _handle_mouse_press(self, mouse_pos: MousePos) -> None:
    if self._open:
      self._consumed_press = True
      if not rl.check_collision_point_rec(mouse_pos, self._panel_rect):
        self._open = False
