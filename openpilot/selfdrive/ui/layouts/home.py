import math
import time
import pyray as rl
from enum import IntEnum
from openpilot.common.params import Params
from openpilot.selfdrive.ui.widgets.offroad_alerts import UpdateAlert, OffroadAlert
from openpilot.selfdrive.ui.widgets.settings_grid import DRIVING_PARAMS, SettingsGrid
from openpilot.selfdrive.ui.widgets.status_bar import StatusBar
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.text_measure import measure_text_cached
from openpilot.system.ui.lib.application import gui_app, FontWeight, MousePos
from openpilot.system.ui.lib.multilang import tr, trn
from openpilot.system.ui.widgets.label import gui_label
from openpilot.system.ui.widgets import Widget

HEADER_HEIGHT = 80
HEAD_BUTTON_FONT_SIZE = 40
CONTENT_MARGIN = 40
SPACING = 25
VERSION_FONT_SIZE = 48
REFRESH_INTERVAL = 10.0

# three columns, which is what the compact controls bought: a choice is one button now rather
# than a row of pills, so a setting no longer needs the width of the page to itself. the page is
# wide and short, so splitting sideways is where the room is, and the rows left over are room
# for settings that do not exist yet.
SETTINGS_COLUMNS = 3
SETTINGS_ROWS = math.ceil(len(DRIVING_PARAMS) / SETTINGS_COLUMNS)
# the row height is worked out from what the page actually has, rather than fixed. a fixed one
# is how the switch row ended up off the bottom of the screen the moment a setting was added:
# nothing checked that the rows still fit. rows shrink instead now, down to a floor that is
# still a fair tap target, and stop growing before the page reads as mostly empty.
SETTINGS_ROW_MIN_HEIGHT = 92
SETTINGS_ROW_MAX_HEIGHT = 150
COLUMN_TITLE_HEIGHT = 66
COLUMN_TITLE_FONT_SIZE = 44


class HomeLayoutState(IntEnum):
  HOME = 0
  UPDATE = 1
  ALERTS = 2


class HomeLayout(Widget):
  def __init__(self):
    super().__init__()
    self.params = Params()

    self.update_alert = UpdateAlert()
    self.offroad_alert = OffroadAlert()

    self._layout_widgets = {HomeLayoutState.UPDATE: self.update_alert, HomeLayoutState.ALERTS: self.offroad_alert}

    self.current_state = HomeLayoutState.HOME
    self.last_refresh = 0

    self.update_available = False
    self.alert_count = 0
    self._version_text = ""
    self._prev_update_available = False
    self._prev_alerts_present = False

    self.header_rect = rl.Rectangle(0, 0, 0, 0)
    self.content_rect = rl.Rectangle(0, 0, 0, 0)

    self.update_notif_rect = rl.Rectangle(0, 0, 200, HEADER_HEIGHT - 10)
    self.alert_notif_rect = rl.Rectangle(0, 0, 220, HEADER_HEIGHT - 10)

    # the home screen is where a drive gets set up, so it carries what changes how the car
    # drives. the rest of the settings stay one tap away in the overlay and in the menu.
    self._settings_grid = self._child(SettingsGrid(DRIVING_PARAMS, SETTINGS_ROWS))
    # the readiness summary shares the settings title row, so it costs no height of its own
    self._status_bar = self._child(StatusBar())
    self._setup_callbacks()

  def show_event(self):
    super().show_event()
    self.last_refresh = time.monotonic()
    self._refresh()

  def _setup_callbacks(self):
    self.update_alert.set_dismiss_callback(lambda: self._set_state(HomeLayoutState.HOME))
    self.offroad_alert.set_dismiss_callback(lambda: self._set_state(HomeLayoutState.HOME))

  def _set_state(self, state: HomeLayoutState):
    # propagate show/hide events
    if state != self.current_state:
      if state == HomeLayoutState.HOME:
        self._settings_grid.refresh()
        if ui_state.show_home_status:
          self._status_bar.refresh()

      if state in self._layout_widgets:
        self._layout_widgets[state].show_event()
      if self.current_state in self._layout_widgets:
        self._layout_widgets[self.current_state].hide_event()

    self.current_state = state

  def _render(self, rect: rl.Rectangle):
    current_time = time.monotonic()
    if current_time - self.last_refresh >= REFRESH_INTERVAL:
      self._refresh()
      self.last_refresh = current_time

    self._render_header()

    # Render content based on current state
    if self.current_state == HomeLayoutState.HOME:
      self._render_home_content()
    elif self.current_state == HomeLayoutState.UPDATE:
      self._render_update_view()
    elif self.current_state == HomeLayoutState.ALERTS:
      self._render_alerts_view()

  def _update_state(self):
    self.header_rect = rl.Rectangle(
      self._rect.x + CONTENT_MARGIN, self._rect.y + CONTENT_MARGIN, self._rect.width - 2 * CONTENT_MARGIN, HEADER_HEIGHT
    )

    content_y = self._rect.y + CONTENT_MARGIN + HEADER_HEIGHT + SPACING
    content_height = self._rect.height - CONTENT_MARGIN - HEADER_HEIGHT - SPACING - CONTENT_MARGIN

    self.content_rect = rl.Rectangle(
      self._rect.x + CONTENT_MARGIN, content_y, self._rect.width - 2 * CONTENT_MARGIN, content_height
    )

    self.update_notif_rect.x = self.header_rect.x
    self.update_notif_rect.y = self.header_rect.y + (self.header_rect.height - 60) // 2

    self.alert_notif_rect.x = self.header_rect.x + (220 if self.update_available else 0)
    self.alert_notif_rect.y = self.header_rect.y + (self.header_rect.height - 60) // 2

  def _handle_mouse_release(self, mouse_pos: MousePos):
    super()._handle_mouse_release(mouse_pos)

    if self.update_available and rl.check_collision_point_rec(mouse_pos, self.update_notif_rect):
      self._set_state(HomeLayoutState.UPDATE)
    elif self.alert_count > 0 and rl.check_collision_point_rec(mouse_pos, self.alert_notif_rect):
      self._set_state(HomeLayoutState.ALERTS)

  def _render_header(self):
    font = gui_app.font(FontWeight.MEDIUM)
    right = self.header_rect.x + self.header_rect.width

    # Update notification button
    if self.update_available:
      # Highlight if currently viewing updates
      highlight_color = rl.Color(75, 95, 255, 255) if self.current_state == HomeLayoutState.UPDATE else rl.Color(54, 77, 239, 255)
      rl.draw_rectangle_rounded(self.update_notif_rect, 0.3, 10, highlight_color)

      text = tr("UPDATE")
      text_size = measure_text_cached(font, text, HEAD_BUTTON_FONT_SIZE)
      text_x = self.update_notif_rect.x + (self.update_notif_rect.width - text_size.x) // 2
      text_y = self.update_notif_rect.y + (self.update_notif_rect.height - text_size.y) // 2
      rl.draw_text_ex(font, text, rl.Vector2(int(text_x), int(text_y)), HEAD_BUTTON_FONT_SIZE, 0, rl.WHITE)

    # Alert notification button
    if self.alert_count > 0:
      # Highlight if currently viewing alerts
      highlight_color = rl.Color(255, 70, 70, 255) if self.current_state == HomeLayoutState.ALERTS else rl.Color(226, 44, 44, 255)
      rl.draw_rectangle_rounded(self.alert_notif_rect, 0.3, 10, highlight_color)

      alert_text = trn("{} ALERT", "{} ALERTS", self.alert_count).format(self.alert_count)
      text_size = measure_text_cached(font, alert_text, HEAD_BUTTON_FONT_SIZE)
      text_x = self.alert_notif_rect.x + (self.alert_notif_rect.width - text_size.x) // 2
      text_y = self.alert_notif_rect.y + (self.alert_notif_rect.height - text_size.y) // 2
      rl.draw_text_ex(font, alert_text, rl.Vector2(int(text_x), int(text_y)), HEAD_BUTTON_FONT_SIZE, 0, rl.WHITE)

    # Version text (right aligned)
    version_width = measure_text_cached(font, self._version_text, VERSION_FONT_SIZE).x
    version_rect = rl.Rectangle(right - version_width, self.header_rect.y, version_width, self.header_rect.height)
    gui_label(version_rect, self._version_text, VERSION_FONT_SIZE, rl.WHITE, alignment=rl.GuiTextAlignment.TEXT_ALIGN_RIGHT)

  def _render_home_content(self):
    rect = self.content_rect
    title = tr("SETTINGS")
    gui_label(rl.Rectangle(rect.x, rect.y, rect.width, COLUMN_TITLE_HEIGHT), title,
              COLUMN_TITLE_FONT_SIZE, font_weight=FontWeight.BOLD)

    # the readiness summary rides beside the title on the same line, and drops its own tail when
    # what the title leaves is not enough for every fact
    if ui_state.show_home_status:
      status_x = rect.x + measure_text_cached(gui_app.font(FontWeight.BOLD), title, COLUMN_TITLE_FONT_SIZE).x + SPACING * 2
      self._status_bar.render(rl.Rectangle(status_x, rect.y, max(0.0, rect.x + rect.width - status_x), COLUMN_TITLE_HEIGHT))

    grid_rect = rl.Rectangle(rect.x, rect.y + COLUMN_TITLE_HEIGHT, rect.width, rect.height - COLUMN_TITLE_HEIGHT)
    row_height = min(SETTINGS_ROW_MAX_HEIGHT, max(SETTINGS_ROW_MIN_HEIGHT, grid_rect.height / SETTINGS_ROWS))
    self._settings_grid.set_row_height(row_height)
    self._settings_grid.render(grid_rect)

  def _render_update_view(self):
    self.update_alert.render(self.content_rect)

  def _render_alerts_view(self):
    self.offroad_alert.render(self.content_rect)

  def _refresh(self):
    self._version_text = self._get_version_text()
    self._settings_grid.refresh()
    if ui_state.show_home_status:
      self._status_bar.refresh()
    update_available = self.update_alert.refresh()
    alert_count = self.offroad_alert.refresh()
    alerts_present = alert_count > 0

    # Show panels on transition from no alert/update to any alerts/update
    if not update_available and not alerts_present:
      self._set_state(HomeLayoutState.HOME)
    elif update_available and ((not self._prev_update_available) or (not alerts_present and self.current_state == HomeLayoutState.ALERTS)):
      self._set_state(HomeLayoutState.UPDATE)
    elif alerts_present and ((not self._prev_alerts_present) or (not update_available and self.current_state == HomeLayoutState.UPDATE)):
      self._set_state(HomeLayoutState.ALERTS)

    self.update_available = update_available
    self.alert_count = alert_count
    self._prev_update_available = update_available
    self._prev_alerts_present = alerts_present

  def _get_version_text(self) -> str:
    brand = "openpilot"
    description = self.params.get("UpdaterCurrentDescription")
    return f"{brand} {description}" if description else brand
