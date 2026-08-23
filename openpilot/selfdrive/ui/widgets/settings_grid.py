"""A compact grid of the fork's settings, laid out in columns.

This is the place to change a setting, either parked on the home screen or over the camera while
driving, so a change can be judged against the road that raised the question. Labels are terse
and untranslated for that reason: they are reminders, not explanations. Tapping one puts the
full explanation on screen, which is the same text the settings menu carries.
"""

import math
from collections.abc import Callable

import pyray as rl

from openpilot.common.params import Params
from openpilot.selfdrive.controls.lib.blinker_pause import ANY_SPEED_MPH, BLINKER_PAUSE_SPEEDS_MPH
from openpilot.selfdrive.controls.lib.lane_position import LANE_POSITION_OFFSETS_CM
from openpilot.selfdrive.ui.layouts.settings.toggles import (AUTO_LANE_CHANGE_TIMERS, BLINKER_PAUSE_DELAYS,
                                                             CURVE_ADVISORY_LEVELS, DESCRIPTIONS)
from openpilot.selfdrive.ui.ui_state import BRIGHTNESS_LEVELS, device, ui_state
from openpilot.system.ui.lib.application import FontWeight, MousePos, gui_app
from openpilot.system.ui.lib.multilang import tr
from openpilot.system.ui.lib.text_measure import measure_text_cached
from openpilot.system.ui.lib.wrap_text import wrap_text
from openpilot.system.ui.widgets import Widget
from openpilot.system.ui.widgets.toggle import Toggle

ROW_HEIGHT = 92
COLUMN_GAP = 60
# the least a label may sit from the control beside it
LABEL_GAP = 40

# a choice used to be a row of pills, one per value. that spends a whole row on a setting that
# is read at a glance and changed rarely, and it is the reason the page ran out of room. one
# button carrying the current value costs a fraction of the width, and what that buys back is
# what lets two settings share a row.
DROPDOWN_HEIGHT = 78
DROPDOWN_PAD = 24
DROPDOWN_CHEVRON = 34
DROPDOWN_MIN_WIDTH = 150
# the button is what you aim at, and the band running past it is what you can hit. same trick as
# the switch below, for the same reason: this gets tapped in a moving car
DROPDOWN_HIT_EXTRA = 110

# the open list. rows are taller than the closed button because this is the part that has to be
# hit exactly, and it is only on screen for the one tap
POPUP_ROW_HEIGHT = 96
POPUP_PAD = 14
POPUP_GAP = 12
POPUP_MARGIN = 24
POPUP_MIN_WIDTH = 220

# Toggle draws itself at a fixed size, these have to match
TOGGLE_WIDTH = 160
TOGGLE_HEIGHT = 80
# ...and 160 x 80 is a small target to hit in a moving car, so the switch takes taps from a band
# of the row that starts at the switch and runs on past it. it never reaches back to the label,
# so a tap that missed the row entirely does not read as a deliberate one
TOGGLE_HIT_WIDTH = 320

LABEL_FONT_SIZE = 38
VALUE_FONT_SIZE = 32

# the card that explains a setting. it is read standing still, so it is sized for reading rather
# than for the room left over: as wide as the screen allows, up to a line length that stays easy
# to follow.
INFO_MAX_WIDTH = 1400
INFO_MARGIN = 60
INFO_PAD = 44
INFO_TITLE_FONT_SIZE = 46
INFO_BODY_FONT_SIZE = 34
INFO_LINE_HEIGHT = 46
INFO_TITLE_GAP = 32
INFO_HINT_GAP = 28
INFO_HINT_FONT_SIZE = 28

# the tabs that pick which grid a page shows. they ride on a title row, so they are shorter than
# a dropdown button and lean on the row's own height for the rest of the tap target
TAB_HEIGHT = 56
TAB_PAD = 30
TAB_GAP = 10

LABEL_COLOR = rl.Color(228, 228, 228, 255)
LABEL_DISABLED_COLOR = rl.Color(120, 120, 120, 255)
SEG_SELECTED = rl.Color(51, 171, 76, 255)
SEG_PRESSED = rl.Color(90, 90, 90, 255)
SEG_BG = rl.Color(57, 57, 57, 255)
SEG_TEXT = rl.Color(228, 228, 228, 255)
SEG_TEXT_DISABLED = rl.Color(130, 130, 130, 255)

POPUP_BG = rl.Color(44, 44, 46, 255)
POPUP_BORDER = rl.Color(255, 255, 255, 55)
POPUP_SHADOW = rl.Color(0, 0, 0, 130)
POPUP_SCRIM = rl.Color(0, 0, 0, 170)
INFO_BODY_COLOR = rl.Color(202, 202, 202, 255)
INFO_HINT_COLOR = rl.Color(130, 130, 130, 255)

# param, label, restarts openpilot when changed
BOOL_SETTINGS = (
  ("MadsEnabled", "MADS", True),
  ("MadsMainSwitch", "Cruise switch", True),
  ("AutoVehicleHold", "Brake hold", True),
  ("DisableStopStart", "Kill auto stop", True),
  ("ReverseGearDebounce", "Ignore reverse", False),
  ("IsLdwEnabled", "Lane departure warn", False),
  ("ShowLeadIndicator", "Lead marker", False),
  ("EngagementPathColor", "Path color by steer", False),
  ("HideExperimentalButton", "Hide exp button", False),
  ("WideCameraLowSpeed", "Wide cam low speed", False),
  ("ShowTurnSignals", "Turn arrows", False),
  ("ShowStockBrake", "Brake bar", False),
  ("ShowBlindSpot", "Blind spot bars", False),
  ("ShowSteeringOnly", "Steering badge", False),
  ("ShowHomeStatus", "Home status", False),
  ("AlwaysOnDM", "Always-on DM", False),
  ("DisengageOnAccelerator", "Disengage on gas", False),
  ("IsMetric", "Metric", False),
)

# param, label, stored values, button labels
# brightness leads: it is the one here that is worth changing without any thought about the
# drive, and the top row is the easiest to hit both parked and over the camera
CHOICE_SETTINGS = (
  ("BrightnessLevel", "Brightness", BRIGHTNESS_LEVELS, ("Auto", "25", "50", "75", "100")),
  ("AutoLaneChangeTimer", "Lane change", AUTO_LANE_CHANGE_TIMERS, ("Nudge", "1s", "2s", "3s")),
  ("BlinkerPauseSpeed", "Blinker pause", BLINKER_PAUSE_SPEEDS_MPH, ("Off", "20", "40", "Any")),
  ("BlinkerPauseDelay", "Resume delay", BLINKER_PAUSE_DELAYS, ("Now", "1s", "2s", "3s")),
  ("CurveAdvisory", "Curve warning", CURVE_ADVISORY_LEVELS, ("Off", "Late", "Norm", "Early")),
  ("LanePosition", "Lane position", LANE_POSITION_OFFSETS_CM, ("FL", "L", "C", "R", "FR")),
)

# what changes how the car drives. this is the set worth having on the home screen, where the
# question is what to try on the next drive rather than what to change during one
DRIVING_PARAMS = tuple(s[0] for s in CHOICE_SETTINGS) + ("MadsEnabled", "MadsMainSwitch", "AutoVehicleHold",
                                                         "DisableStopStart", "ReverseGearDebounce")

# and what only changes how the screen looks. ShowDebugPanel is deliberately not here: it is the
# switch for the driving overlay, and putting it inside that overlay is a door that locks behind
# you. It stays in the settings menu, which is reachable either way.
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

  def _render(self, rect: rl.Rectangle) -> None:
    band = self._rect
    self._rect = rl.Rectangle(band.x, band.y + (band.height - TOGGLE_HEIGHT) / 2, TOGGLE_WIDTH, TOGGLE_HEIGHT)
    try:
      return super()._render(self._rect)
    finally:
      self._rect = band


def _draw_chevron(x: float, y: float, pointing_up: bool, color: rl.Color) -> None:
  """The little arrow that says there is more behind this button."""
  half, rise = 11.0, 6.0
  tip_y = y - rise if pointing_up else y + rise
  base_y = y + rise if pointing_up else y - rise
  for dx in (-half, half):
    rl.draw_line_ex(rl.Vector2(x + dx, base_y), rl.Vector2(x, tip_y), 4, color)


class Dropdown(Widget):
  """One button carrying the current choice, with the rest of the values behind a tap.

  Opening is not handled here. The grid owns the open list, because it has to be drawn over
  every row rather than inside the one it belongs to, and because only one may be open at a
  time.
  """

  def __init__(self, texts: tuple[str, ...], selected: int, on_open: Callable[[str], None], param: str):
    super().__init__()
    self._texts = texts
    self._selected = selected
    self._on_open = on_open
    self._param = param
    self._font = gui_app.font(FontWeight.MEDIUM)
    self._is_open = False

    widest = max(measure_text_cached(self._font, t, VALUE_FONT_SIZE).x for t in texts)
    self._natural_width = max(DROPDOWN_MIN_WIDTH, int(widest + 2 * DROPDOWN_PAD + DROPDOWN_CHEVRON))
    self._width = self._natural_width

  @property
  def natural_width(self) -> int:
    return self._natural_width

  def set_width(self, width: int) -> None:
    self._width = width

  @property
  def width(self) -> int:
    return self._width

  @property
  def texts(self) -> tuple[str, ...]:
    return self._texts

  @property
  def selected(self) -> int:
    return self._selected

  def set_selected(self, index: int) -> None:
    self._selected = index

  def set_open(self, is_open: bool) -> None:
    self._is_open = is_open

  @property
  def button_rect(self) -> rl.Rectangle:
    """Where the button actually draws, which is what the open list anchors to."""
    return rl.Rectangle(self._rect.x, self._rect.y + (self._rect.height - DROPDOWN_HEIGHT) / 2,
                        self._width, DROPDOWN_HEIGHT)

  def _render(self, _: rl.Rectangle) -> None:
    button = self.button_rect
    if self._is_open:
      color = SEG_SELECTED
    elif self.enabled and self.is_pressed:
      color = SEG_PRESSED
    else:
      color = SEG_BG
    if not self.enabled:
      color = rl.Color(color.r, color.g, color.b, 110)
    rl.draw_rectangle_rounded(button, 1.0, 20, color)

    text = self._texts[self._selected]
    text_size = measure_text_cached(self._font, text, VALUE_FONT_SIZE)
    text_color = SEG_TEXT if self.enabled else SEG_TEXT_DISABLED
    rl.draw_text_ex(self._font, text, rl.Vector2(button.x + DROPDOWN_PAD, button.y + (DROPDOWN_HEIGHT - text_size.y) / 2),
                    VALUE_FONT_SIZE, 0, text_color)

    _draw_chevron(button.x + button.width - DROPDOWN_PAD - DROPDOWN_CHEVRON / 2, button.y + DROPDOWN_HEIGHT / 2,
                  self._is_open, text_color)

  def _handle_mouse_release(self, _: MousePos) -> None:
    self._on_open(self._param)


class DropdownList(Widget):
  """The options of the open dropdown, drawn over the rest of the grid.

  It takes the whole screen as its rect, so a tap anywhere lands here: on an option it picks
  that value, anywhere else it closes. The grid stops every other control from answering to
  touch while this is up, so one tap can never both pick a value here and change what happens
  to be underneath the list.
  """

  def __init__(self):
    super().__init__()
    self._font = gui_app.font(FontWeight.MEDIUM)
    self._texts: tuple[str, ...] = ()
    self._selected = 0
    self._anchor = rl.Rectangle(0, 0, 0, 0)
    self._on_select: Callable[[int], None] = lambda _: None
    self._on_close: Callable[[], None] = lambda: None

  def open(self, texts: tuple[str, ...], selected: int, anchor: rl.Rectangle,
           on_select: Callable[[int], None], on_close: Callable[[], None]) -> None:
    self._texts = texts
    self._selected = selected
    self._anchor = anchor
    self._on_select = on_select
    self._on_close = on_close

  def _panel_rect(self) -> rl.Rectangle:
    width = max(POPUP_MIN_WIDTH, self._anchor.width)
    height = len(self._texts) * POPUP_ROW_HEIGHT + 2 * POPUP_PAD

    x = max(POPUP_MARGIN, min(self._anchor.x, gui_app.width - width - POPUP_MARGIN))

    # under the button by default, flipped above when the bottom of the screen is in the way. a
    # list that runs off the edge would hide the values furthest from the current one
    y = self._anchor.y + self._anchor.height + POPUP_GAP
    if y + height > gui_app.height - POPUP_MARGIN:
      y = self._anchor.y - POPUP_GAP - height
    y = max(POPUP_MARGIN, min(y, gui_app.height - height - POPUP_MARGIN))

    return rl.Rectangle(x, y, width, height)

  def _option_rect(self, panel: rl.Rectangle, index: int) -> rl.Rectangle:
    return rl.Rectangle(panel.x + POPUP_PAD, panel.y + POPUP_PAD + index * POPUP_ROW_HEIGHT,
                        panel.width - 2 * POPUP_PAD, POPUP_ROW_HEIGHT)

  def _render(self, _: rl.Rectangle) -> None:
    panel = self._panel_rect()

    # the list sits over rows that look a lot like it, so it needs an edge of its own to read as
    # something in front rather than something else in the grid
    shadow = rl.Rectangle(panel.x - 6, panel.y - 4, panel.width + 12, panel.height + 14)
    rl.draw_rectangle_rounded(shadow, 0.08, 20, POPUP_SHADOW)
    rl.draw_rectangle_rounded(panel, 0.08, 20, POPUP_BG)
    rl.draw_rectangle_rounded_lines_ex(panel, 0.08, 20, 2, POPUP_BORDER)

    mouse_pos = rl.get_mouse_position()
    for i, text in enumerate(self._texts):
      option = self._option_rect(panel, i)
      if i == self._selected:
        rl.draw_rectangle_rounded(option, 0.35, 20, SEG_SELECTED)
      elif self.is_pressed and rl.check_collision_point_rec(mouse_pos, option):
        rl.draw_rectangle_rounded(option, 0.35, 20, SEG_PRESSED)

      text_size = measure_text_cached(self._font, text, VALUE_FONT_SIZE)
      rl.draw_text_ex(self._font, text, rl.Vector2(option.x + DROPDOWN_PAD, option.y + (option.height - text_size.y) / 2),
                      VALUE_FONT_SIZE, 0, SEG_TEXT)

  def _handle_mouse_release(self, mouse_pos: MousePos) -> None:
    panel = self._panel_rect()
    for i in range(len(self._texts)):
      if rl.check_collision_point_rec(mouse_pos, self._option_rect(panel, i)):
        self._on_select(i)
        return
    self._on_close()


class InfoPopup(Widget):
  """What a setting actually does, on a card over the page.

  The grid labels are short enough to be read at a glance, which also makes several of them
  meaningless on their own. This carries the settings menu's own wording, so the compact grid
  stops depending on having read the menu first.

  Like the option list, it takes the whole screen as its rect, so any tap closes it and no tap
  reaches whatever it is covering.
  """

  def __init__(self):
    super().__init__()
    self._title_font = gui_app.font(FontWeight.BOLD)
    self._body_font = gui_app.font(FontWeight.MEDIUM)
    self._title = ""
    self._body = ""
    self._on_close: Callable[[], None] = lambda: None

  def open(self, title: str, body: str, on_close: Callable[[], None]) -> None:
    self._title = title
    self._body = body
    self._on_close = on_close

  def _wrapped(self, width: float) -> list[str]:
    return wrap_text(self._body_font, self._body, INFO_BODY_FONT_SIZE, int(width - 2 * INFO_PAD))

  def _card_rect(self) -> tuple[rl.Rectangle, list[str]]:
    width = min(INFO_MAX_WIDTH, gui_app.width - 2 * INFO_MARGIN)
    lines = self._wrapped(width)
    height = (2 * INFO_PAD + INFO_TITLE_FONT_SIZE + INFO_TITLE_GAP + len(lines) * INFO_LINE_HEIGHT
              + INFO_HINT_GAP + INFO_HINT_FONT_SIZE)
    height = min(height, gui_app.height - 2 * INFO_MARGIN)
    return rl.Rectangle((gui_app.width - width) / 2, (gui_app.height - height) / 2, width, height), lines

  def _render(self, _: rl.Rectangle) -> None:
    # the page underneath is a grid of controls, so it has to go dim: a card floating over live
    # switches reads as one more thing to press
    rl.draw_rectangle(0, 0, gui_app.width, gui_app.height, POPUP_SCRIM)

    card, lines = self._card_rect()
    rl.draw_rectangle_rounded(card, 0.05, 20, POPUP_BG)
    rl.draw_rectangle_rounded_lines_ex(card, 0.05, 20, 2, POPUP_BORDER)

    x = card.x + INFO_PAD
    y = card.y + INFO_PAD
    rl.draw_text_ex(self._title_font, self._title, rl.Vector2(x, y), INFO_TITLE_FONT_SIZE, 0, LABEL_COLOR)
    y += INFO_TITLE_FONT_SIZE + INFO_TITLE_GAP

    for line in lines:
      rl.draw_text_ex(self._body_font, line, rl.Vector2(x, y), INFO_BODY_FONT_SIZE, 0, INFO_BODY_COLOR)
      y += INFO_LINE_HEIGHT

    hint = tr("tap anywhere to close")
    rl.draw_text_ex(self._body_font, hint, rl.Vector2(x, y + INFO_HINT_GAP), INFO_HINT_FONT_SIZE, 0, INFO_HINT_COLOR)

  def _handle_mouse_release(self, _: MousePos) -> None:
    self._on_close()


class SettingsTabs(Widget):
  """Pills that pick which grid a page is showing.

  Two grids in the same place need something to say which one is up. Tabs rather than a second
  page because both sets are short enough to fit, so the only cost of switching is the tap, and
  the answer to "where did that setting go" stays visible on screen.
  """

  def __init__(self, labels: tuple[str, ...], on_select: Callable[[int], None], selected: int = 0):
    super().__init__()
    self._labels = labels
    self._on_select = on_select
    self._selected = selected
    self._font = gui_app.font(FontWeight.MEDIUM)

    # every pill takes the width of the widest label, so switching does not shuffle them
    widest = max(measure_text_cached(self._font, label, VALUE_FONT_SIZE).x for label in labels)
    self._pill_width = int(widest + 2 * TAB_PAD)
    self._natural_width = len(labels) * self._pill_width + (len(labels) - 1) * TAB_GAP

  @property
  def natural_width(self) -> int:
    return self._natural_width

  @property
  def selected(self) -> int:
    return self._selected

  def set_selected(self, index: int) -> None:
    self._selected = index

  def _pill_rect(self, index: int) -> rl.Rectangle:
    return rl.Rectangle(self._rect.x + index * (self._pill_width + TAB_GAP),
                        self._rect.y + (self._rect.height - TAB_HEIGHT) / 2,
                        self._pill_width, TAB_HEIGHT)

  def _render(self, _: rl.Rectangle) -> None:
    for i, label in enumerate(self._labels):
      pill = self._pill_rect(i)
      color = SEG_SELECTED if i == self._selected else SEG_BG
      rl.draw_rectangle_rounded(pill, 1.0, 20, color)

      size = measure_text_cached(self._font, label, VALUE_FONT_SIZE)
      pos = rl.Vector2(pill.x + (pill.width - size.x) / 2, pill.y + (pill.height - size.y) / 2)
      rl.draw_text_ex(self._font, label, pos, VALUE_FONT_SIZE, 0, SEG_TEXT)

  def _handle_mouse_release(self, mouse_pos: MousePos) -> None:
    for i in range(len(self._labels)):
      if rl.check_collision_point_rec(mouse_pos, self._pill_rect(i)):
        if i != self._selected:
          self._selected = i
          self._on_select(i)
        return


class SettingsGrid(Widget):
  """Label on the left, control on the right, filled column by column."""

  def __init__(self, param_names: tuple[str, ...], rows_per_column: int, row_height: int = ROW_HEIGHT):
    super().__init__()
    self._params = Params()
    self._param_names = param_names
    self._rows_per_column = rows_per_column
    self._row_height = row_height
    self._font = gui_app.font(FontWeight.MEDIUM)

    self._columns = math.ceil(len(param_names) / rows_per_column)

    self._labels = {s[0]: s[1] for s in BOOL_SETTINGS} | {s[0]: s[1] for s in CHOICE_SETTINGS}
    self._restarts = {s[0] for s in BOOL_SETTINGS if s[2]} & set(param_names)
    self._choice_values = {s[0]: s[2] for s in CHOICE_SETTINGS if s[0] in param_names}

    self._toggles: dict[str, RowToggle] = {}
    for param, _, _ in BOOL_SETTINGS:
      if param in param_names:
        self._toggles[param] = RowToggle(initial_state=self._params.get_bool(param),
                                         callback=lambda state, p=param: self._set_bool(p, state))

    self._dropdowns: dict[str, Dropdown] = {}
    for param, _, _, texts in CHOICE_SETTINGS:
      if param in param_names:
        self._dropdowns[param] = Dropdown(texts, self._selected_index(param), self._open_dropdown, param)

    self._controls: dict[str, Widget] = {**self._toggles, **self._dropdowns}

    # only one list is ever up, so one widget serves every dropdown
    self._open_param: str | None = None
    self._popup = DropdownList()

    # tapping a label explains that setting. the rects are whatever the last frame drew, since
    # the row height and the column width both depend on the page the grid is on
    self._label_rects: dict[str, rl.Rectangle] = {}
    self._info = InfoPopup()
    self._info_param: str | None = None
    # a card put away by this frame's tap must not let the same tap open another one
    self._popup_was_open = False

    # while anything is up over the grid nothing else may take a touch, or the tap that picks a
    # value also lands on whatever row it happens to be covering
    for control in self._controls.values():
      control.set_touch_valid_callback(lambda: not self.is_popup_open)

    # one button width for every dropdown, so they line up down a column
    self._button_width = max((d.natural_width for d in self._dropdowns.values()), default=0)
    for dropdown in self._dropdowns.values():
      dropdown.set_width(self._button_width)

    self._widest_label = max((measure_text_cached(self._font, self._labels[p], LABEL_FONT_SIZE).x
                              for p in param_names), default=0.0)

  @property
  def columns(self) -> int:
    return self._columns

  @property
  def rows(self) -> int:
    return min(len(self._param_names), self._rows_per_column)

  @property
  def is_popup_open(self) -> bool:
    """True while anything is up over the grid, so a container can leave the touch to it."""
    return self._open_param is not None or self._info_param is not None

  def height_hint(self) -> float:
    return self.rows * self._row_height

  def set_row_height(self, row_height: float) -> None:
    self._row_height = row_height

  def column_width(self, total_width: float) -> float:
    return (total_width - (self._columns - 1) * COLUMN_GAP) / self._columns

  def show_event(self) -> None:
    super().show_event()
    self.refresh()

  def hide_event(self) -> None:
    super().hide_event()
    self._close_dropdown()

  def close_popup(self) -> None:
    """Put any open list or card away. A container that hides the grid has to call this.

    Either one is what stops everything else answering to touch, so one left open behind a
    hidden grid would lock out whatever brings the grid back.
    """
    self._close_dropdown()
    self._close_info()

  def refresh(self) -> None:
    """Pull every control back from params, so the grid never shows a stale value."""
    self._close_dropdown()
    self._close_info()
    for param, toggle in self._toggles.items():
      toggle.set_state(self._params.get_bool(param))
    for param, dropdown in self._dropdowns.items():
      dropdown.set_selected(self._selected_index(param))

  def _open_dropdown(self, param: str) -> None:
    # a second tap on the same button puts the list away again
    if self._open_param == param:
      self._close_dropdown()
      return

    self._close_dropdown()
    dropdown = self._dropdowns[param]
    self._open_param = param
    dropdown.set_open(True)
    self._popup.open(dropdown.texts, dropdown.selected, dropdown.button_rect,
                     lambda index, p=param: self._pick_choice(p, index), self._close_dropdown)

  def _close_dropdown(self) -> None:
    if self._open_param is not None:
      self._dropdowns[self._open_param].set_open(False)
      self._open_param = None

  def _open_info(self, param: str) -> None:
    self._close_dropdown()
    self._info_param = param
    self._info.open(self._labels[param], tr(DESCRIPTIONS[param]), self._close_info)

  def _close_info(self) -> None:
    self._info_param = None

  def _pick_choice(self, param: str, index: int) -> None:
    self._dropdowns[param].set_selected(index)
    self._set_choice(param, index)
    self._close_dropdown()

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
    if "BlinkerPauseSpeed" in self._dropdowns:
      pause_speed = BLINKER_PAUSE_SPEEDS_MPH[self._dropdowns["BlinkerPauseSpeed"].selected]
      if "BlinkerPauseDelay" in self._dropdowns:
        self._dropdowns["BlinkerPauseDelay"].set_enabled(pause_speed > 0)
      if "AutoLaneChangeTimer" in self._dropdowns:
        self._dropdowns["AutoLaneChangeTimer"].set_enabled(pause_speed < ANY_SPEED_MPH)

    # a control that goes disabled under an open list would never get the tap that closes it
    if self._open_param is not None and not self._dropdowns[self._open_param].enabled:
      self._close_dropdown()

  def _render(self, rect: rl.Rectangle) -> None:
    # read before anything opened by this frame's tap, and before anything closed by it
    self._popup_was_open = self.is_popup_open
    column_width = self.column_width(rect.width)

    for i, param in enumerate(self._param_names):
      control = self._controls[param]
      x, y = self._slot_origin(rect, i, column_width)

      is_toggle = isinstance(control, RowToggle)
      drawn_width = TOGGLE_WIDTH if is_toggle else control.width
      band_width = TOGGLE_HIT_WIDTH if is_toggle else control.width + DROPDOWN_HIT_EXTRA

      self._draw_label(param, x, y, control.enabled)

      # the controls sit just past the longest label rather than out at the column edge: the
      # driver sits to the left of this screen, so the far right is the worst place to reach.
      # what has to fit in the column is the control as drawn, not the band of touch around it,
      # or a narrow column pulls the control back over its own label to make room for a band
      # that was never visible in the first place.
      control_x = min(x + self._widest_label + LABEL_GAP, x + column_width - drawn_width)

      # the band may run past the column into the gap beside it, which is empty, but never as
      # far as the next column's control
      band_width = max(drawn_width, min(band_width, x + column_width + COLUMN_GAP - control_x))

      # the label answers to everything from the left edge of the row up to the control's own
      # band. reading a setting is done standing still, so this is a generous target that can
      # afford to be: it never reaches the control, so it cannot swallow a tap meant for one
      self._label_rects[param] = rl.Rectangle(x, y, max(0.0, control_x - x), self._row_height)

      # both controls take the whole band, and place their own smaller visuals inside it
      control.render(rl.Rectangle(control_x, y, band_width, self._row_height))

    # last, so what is up covers the rows rather than the rows covering it
    if self._info_param is not None:
      self._info.render(rl.Rectangle(0, 0, gui_app.width, gui_app.height))
    elif self._open_param is not None:
      self._popup.render(rl.Rectangle(0, 0, gui_app.width, gui_app.height))

  def _handle_mouse_release(self, mouse_pos: MousePos) -> None:
    # the card and the option list both draw over the rows, so while one is up its own tap has
    # already been dealt with by the time this runs
    if self._popup_was_open:
      return

    for param, label_rect in self._label_rects.items():
      if param in DESCRIPTIONS and rl.check_collision_point_rec(mouse_pos, label_rect):
        self._open_info(param)
        return

  def _slot_origin(self, rect: rl.Rectangle, slot: int, column_width: float) -> tuple[float, float]:
    return (rect.x + (slot // self._rows_per_column) * (column_width + COLUMN_GAP),
            rect.y + (slot % self._rows_per_column) * self._row_height)

  def _draw_label(self, param: str, x: float, y: float, enabled: bool) -> None:
    label_size = measure_text_cached(self._font, self._labels[param], LABEL_FONT_SIZE)
    rl.draw_text_ex(self._font, self._labels[param], rl.Vector2(x, y + (self._row_height - label_size.y) / 2),
                    LABEL_FONT_SIZE, 0, LABEL_COLOR if enabled else LABEL_DISABLED_COLOR)
