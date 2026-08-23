"""On-screen settings panel for the driving view.

The grid itself is shared with the home screen. This adds the parts specific to putting it over
a live camera: a button to open it, a scrim so the road does not read through it, and the touch
handling that keeps a tap on the panel from reaching the road view underneath.
"""

from collections.abc import Callable

import pyray as rl

from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.selfdrive.ui.widgets.settings_grid import ALL_PARAMS, DRIVING_PARAMS, SettingsGrid
from openpilot.system.ui.lib.application import FontWeight, MousePos, gui_app
from openpilot.system.ui.lib.text_measure import measure_text_cached
from openpilot.system.ui.widgets import Widget

# the driving settings fill the left column, so the display ones start the right column and its
# last slot falls free for the button to sit in
ROWS_PER_COLUMN = len(DRIVING_PARAMS)
HEADER_HEIGHT = 66
PANEL_PADDING = 28
PANEL_INSET = 30
ROW_HEIGHT = 92

BUTTON_RADIUS = 46

HEADER_FONT_SIZE = 44
HINT_FONT_SIZE = 30

PANEL_BG = rl.Color(18, 18, 20, 242)
PANEL_BORDER = rl.Color(255, 255, 255, 60)
SCRIM = rl.Color(0, 0, 0, 140)
HEADER_COLOR = rl.Color(255, 255, 255, 255)
HINT_COLOR = rl.Color(140, 140, 140, 255)
BUTTON_BG = rl.Color(0, 0, 0, 166)
BUTTON_GLYPH = rl.Color(255, 255, 255, 255)


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
    self._open = False
    # a press the panel handled itself, so the road view does not also treat it as a tap
    self._consumed_press = False

    self._font_medium = gui_app.font(FontWeight.MEDIUM)
    self._font_bold = gui_app.font(FontWeight.BOLD)

    self._panel_rect = rl.Rectangle(0, 0, 0, 0)
    self._grid_rect = rl.Rectangle(0, 0, 0, 0)
    self._button = DebugButton(self._toggle_open)
    self._grid = SettingsGrid(ALL_PARAMS, ROWS_PER_COLUMN, ROW_HEIGHT)

    # an open option list covers whatever is under it, the button included, so the tap that
    # picks a value must not also reach the button and shut the panel
    self._button.set_touch_valid_callback(lambda: not self._grid.is_popup_open)

    assert self._grid.columns == 2, "the panel is laid out for two columns"
    assert len(ALL_PARAMS) < 2 * ROWS_PER_COLUMN, "the last slot has to stay free for the button"

  @property
  def is_open(self) -> bool:
    return self._open

  def user_interacting(self) -> bool:
    """True when the road view should ignore the current touch."""
    if not ui_state.show_debug_panel:
      return False
    return self._open or self._consumed_press or self._button.is_pressed

  def _toggle_open(self) -> None:
    self._open = not self._open
    if self._open:
      self._grid.refresh()
    else:
      self._grid.close_popup()

  def _update_layout_rects(self) -> None:
    height = ROWS_PER_COLUMN * ROW_HEIGHT + HEADER_HEIGHT + 2 * PANEL_PADDING
    self._panel_rect = rl.Rectangle(
      self._rect.x + PANEL_INSET,
      self._rect.y + (self._rect.height - height) / 2,
      self._rect.width - 2 * PANEL_INSET,
      height,
    )
    self._grid_rect = rl.Rectangle(
      self._panel_rect.x + PANEL_PADDING,
      self._panel_rect.y + PANEL_PADDING + HEADER_HEIGHT,
      self._panel_rect.width - 2 * PANEL_PADDING,
      self._grid.height_hint(),
    )

    # the button parks in the empty last slot of the right column, so it never moves when the
    # panel opens and a second tap in the same place closes it again
    row_center_y = self._grid_rect.y + (ROWS_PER_COLUMN - 1) * ROW_HEIGHT + ROW_HEIGHT / 2
    self._button.set_rect(rl.Rectangle(
      self._grid_rect.x + self._grid_rect.width - 2 * BUTTON_RADIUS,
      row_center_y - BUTTON_RADIUS,
      2 * BUTTON_RADIUS,
      2 * BUTTON_RADIUS,
    ))

  def _update_state(self) -> None:
    # turning the toggle off mid-drive has to close the panel too, or it stays on screen with
    # nothing left to dismiss it
    if not ui_state.show_debug_panel:
      self._open = False

    if not self._open:
      self._grid.close_popup()

    self._button.set_open(self._open)

  def _render(self, rect: rl.Rectangle) -> None:
    self._consumed_press = False
    if not ui_state.show_debug_panel:
      return

    if self._open:
      rl.draw_rectangle_rec(rect, SCRIM)
      rl.draw_rectangle_rounded(self._panel_rect, 0.03, 20, PANEL_BG)
      rl.draw_rectangle_rounded_lines_ex(self._panel_rect, 0.03, 20, 2, PANEL_BORDER)
      self._draw_header()
      # the button goes down before the grid, so an option list opened near it draws over it
      # rather than under it
      self._button.render()
      self._grid.render(self._grid_rect)
    else:
      self._button.render()

  def _draw_header(self) -> None:
    x = self._panel_rect.x + PANEL_PADDING
    y = self._panel_rect.y + PANEL_PADDING
    rl.draw_text_ex(self._font_bold, "DEBUG", rl.Vector2(x, y), HEADER_FONT_SIZE, 0, HEADER_COLOR)

    hint = "changes apply live, MADS needs a restart"
    hint_width = measure_text_cached(self._font_medium, hint, HINT_FONT_SIZE).x
    hint_x = self._panel_rect.x + self._panel_rect.width - PANEL_PADDING - hint_width
    rl.draw_text_ex(self._font_medium, hint, rl.Vector2(hint_x, y + 12), HINT_FONT_SIZE, 0, HINT_COLOR)

  def _handle_mouse_press(self, mouse_pos: MousePos) -> None:
    if self._open:
      self._consumed_press = True
      # an option list may hang outside the panel, so while one is up a press out there is
      # aimed at the list and closing the whole panel would be the wrong answer
      if not self._grid.is_popup_open and not rl.check_collision_point_rec(mouse_pos, self._panel_rect):
        self._open = False
