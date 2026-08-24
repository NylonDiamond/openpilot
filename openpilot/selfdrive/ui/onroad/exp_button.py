import time
import pyray as rl
from openpilot.common.filter_simple import FirstOrderFilter
from openpilot.common.params import Params
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.application import gui_app
from openpilot.system.ui.widgets import Widget

# raylib turns a texture clockwise for a positive angle, and carState.steeringAngleDeg is
# positive to the left, so the drawn angle is the negated one
WHEEL_ROTATION_SIGN = -1.0

# short enough that the icon still tracks the wheel, long enough to take the step out of a
# 100 Hz signal sampled once a frame
WHEEL_FILTER_TAU = 0.05


class ExpButton(Widget):
  def __init__(self, button_size: int, icon_size: int):
    super().__init__()
    self._params = Params()
    self._experimental_mode: bool = False
    self._engageable: bool = False
    self._wheel_filter = FirstOrderFilter(0.0, WHEEL_FILTER_TAU, 1 / gui_app.target_fps)

    # State hold mechanism
    self._hold_duration = 2.0  # seconds
    self._held_mode: bool | None = None
    self._hold_end_time: float | None = None

    self._white_color: rl.Color = rl.Color(255, 255, 255, 255)
    self._black_bg: rl.Color = rl.Color(0, 0, 0, 166)
    self._txt_wheel: rl.Texture = gui_app.texture('icons/chffr_wheel.png', icon_size, icon_size)
    self._txt_exp: rl.Texture = gui_app.texture('icons/experimental.png', icon_size, icon_size)
    self._rect = rl.Rectangle(0, 0, button_size, button_size)

  def set_rect(self, rect: rl.Rectangle) -> None:
    self._rect.x, self._rect.y = rect.x, rect.y

  def _update_state(self) -> None:
    selfdrive_state = ui_state.sm["selfdriveState"]
    self._experimental_mode = selfdrive_state.experimentalMode
    self._engageable = selfdrive_state.engageable or selfdrive_state.enabled

    # unwinding to center while offroad reads as the wheel actually being straightened, which is
    # the only honest thing to show once carState stops arriving
    stale = ui_state.sm.recv_frame["carState"] < ui_state.started_frame
    angle = 0.0 if stale or not ui_state.rotate_wheel_icon else ui_state.sm["carState"].steeringAngleDeg
    self._wheel_filter.update(angle)

  def _handle_mouse_release(self, _):
    super()._handle_mouse_release(_)
    if self._is_toggle_allowed():
      new_mode = not self._experimental_mode
      self._params.put_bool("ExperimentalMode", new_mode)

      # Hold new state temporarily
      self._held_mode = new_mode
      self._hold_end_time = time.monotonic() + self._hold_duration

  def _render(self, rect: rl.Rectangle) -> None:
    center_x = int(self._rect.x + self._rect.width // 2)
    center_y = int(self._rect.y + self._rect.height // 2)

    self._white_color.a = 180 if self.is_pressed or not self._engageable else 255

    is_wheel = not self._held_or_actual_mode()
    texture = self._txt_wheel if is_wheel else self._txt_exp
    rl.draw_circle(center_x, center_y, self._rect.width / 2, self._black_bg)

    # only the wheel turns. the experimental icon is not a wheel, so spinning it means nothing
    if is_wheel and ui_state.rotate_wheel_icon:
      # draw_texture_ex turns about the top left corner, so a centered spin needs the pro form
      source = rl.Rectangle(0, 0, texture.width, texture.height)
      dest = rl.Rectangle(center_x, center_y, texture.width, texture.height)
      origin = rl.Vector2(texture.width / 2, texture.height / 2)
      angle = WHEEL_ROTATION_SIGN * self._wheel_filter.x
      rl.draw_texture_pro(texture, source, dest, origin, angle, self._white_color)
    else:
      rl.draw_texture_ex(texture, rl.Vector2(center_x - texture.width / 2, center_y - texture.height / 2), 0.0, 1.0, self._white_color)

  def _held_or_actual_mode(self):
    now = time.monotonic()
    if self._hold_end_time and now < self._hold_end_time:
      return self._held_mode

    if self._hold_end_time and now >= self._hold_end_time:
      self._hold_end_time = self._held_mode = None

    return self._experimental_mode

  def _is_toggle_allowed(self):
    if not self._params.get_bool("ExperimentalModeConfirmed"):
      return False

    # Mirror exp mode toggle using persistent car params
    return ui_state.has_longitudinal_control
