"""What the home screen used to spend on advertising: whether this thing is ready to drive.

It rides in the top bar, so it is a strip rather than a panel, and every fact has to earn its
width. Values say what they are ("0.20 s lag", not "lag: 0.20 s") because a key beside each one
costs about a third of the bar and tells you nothing you could not read off the value.

Everything here is readable while parked, which rules out anything only published onroad.
Calibration comes from the stored param rather than the extrinsicsCalibration message for that reason,
and the car comes from CarParamsPersistent, which is also what tells the rest of the UI what it
is bolted to.
"""

import math
import time

import pyray as rl

from openpilot.cereal import log, messaging
from openpilot.common.params import Params
from openpilot.common.swaglog import cloudlog
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.application import FontWeight, gui_app
from openpilot.system.ui.lib.text_measure import measure_text_cached
from openpilot.system.ui.widgets import Widget

VALUE_COLOR = rl.Color(228, 228, 228, 255)
GOOD_COLOR = rl.Color(134, 255, 78, 255)
WARN_COLOR = rl.Color(255, 179, 0, 255)
SEPARATOR_COLOR = rl.Color(110, 110, 110, 255)

FONT_SIZE = 28
# wide enough that two facts do not read as one sentence
ITEM_GAP = 18
# a middle dot would be better, but the font only carries the codepoints in EXTRA_FONT_CHARS
# and that is not one of them. anything missing draws as a question mark.
SEPARATOR = "•"

# the slow reads are params and capnp decodes, neither of which changes between drives
REFRESH_INTERVAL = 10.0

# device is fine well past this, but a comma that has been sitting in the sun is worth noticing
WARM_TEMP_C = 75.0
LOW_SPACE_PERCENT = 10.0

CALIBRATED = log.ExtrinsicsCalibration.Status.calibrated
LAG_ESTIMATED = log.LateralDelay.Status.estimated


class StatusBar(Widget):
  """A read-only summary of the car, the calibration, the panda and the device, in one line."""

  def __init__(self):
    super().__init__()
    self._params = Params()
    self._font_medium = gui_app.font(FontWeight.MEDIUM)

    self._last_refresh = 0.0
    self._calibration = ""
    self._calibration_ok = False
    self._steer_lag = ""
    self._steer_lag_ok = False
    self._route_count = ""
    self.refresh()

  def show_event(self) -> None:
    super().show_event()
    self.refresh()

  def refresh(self) -> None:
    self._last_refresh = time.monotonic()
    self._calibration, self._calibration_ok = self._read_calibration()
    self._steer_lag, self._steer_lag_ok = self._read_steer_lag()
    routes = self._params.get("RouteCount", return_default=True)
    self._route_count = str(routes) if routes is not None else "unknown"

  def _read_calibration(self) -> tuple[str, bool]:
    calib_bytes = self._params.get("CalibrationParams")
    if not calib_bytes:
      return "not calibrated", False

    try:
      calib = messaging.log_from_bytes(calib_bytes, log.Event).extrinsicsCalibration
    except Exception:
      cloudlog.exception("invalid CalibrationParams")
      return "unreadable", False

    if calib.calStatus != CALIBRATED or len(calib.rpyCalib) != 3:
      return "calibrating", False

    pitch = math.degrees(calib.rpyCalib[1])
    yaw = math.degrees(calib.rpyCalib[2])
    pitch_text = f"{abs(pitch):.1f}° {'down' if pitch > 0 else 'up'}"
    yaw_text = f"{abs(yaw):.1f}° {'left' if yaw > 0 else 'right'}"
    return f"{pitch_text}, {yaw_text}", True

  def _read_steer_lag(self) -> tuple[str, bool]:
    # CarParams.steerActuatorDelay is only lagd's seed, so it is not what the car is steering
    # on. The learned value is, and it is worth seeing whether it has been measured yet.
    lag_bytes = self._params.get("LiveDelay")
    if not lag_bytes:
      return "not measured", False

    try:
      lag = messaging.log_from_bytes(lag_bytes, log.Event).lateralDelay
    except Exception:
      cloudlog.exception("invalid LiveDelay")
      return "unreadable", False

    # the value it reports before it has estimated is a fallback, not a measurement, so
    # showing that number would read as though the car had been measured when it has not
    if lag.status != LAG_ESTIMATED:
      return "measuring", False
    return f"{lag.lateralDelay:.2f} s lag", True

  def _update_state(self) -> None:
    if time.monotonic() - self._last_refresh >= REFRESH_INTERVAL:
      self.refresh()

  def _items(self) -> list[tuple[str, rl.Color]]:
    CP = ui_state.CP
    device_state = ui_state.sm["deviceState"]

    # the car's fixed specs are a build-time fact rather than a readiness one, so they are not
    # here. what is worth a glance before a drive is what the car has learned about itself.
    items: list[tuple[str, rl.Color]] = []
    if CP is None:
      items.append(("no car seen yet", WARN_COLOR))
    items.append((self._calibration, GOOD_COLOR if self._calibration_ok else WARN_COLOR))
    items.append((self._steer_lag, GOOD_COLOR if self._steer_lag_ok else WARN_COLOR))

    # the type only says whether a panda answered, and the safety model only says which mode it
    # booted into, so they travel together
    panda_type = str(ui_state.panda_type)
    if panda_type == "unknown":
      items.append(("no panda", WARN_COLOR))
    else:
      safety = str(CP.safetyConfigs[-1].safetyModel) if CP is not None and len(CP.safetyConfigs) else ""
      items.append((f"{panda_type}, {safety}" if safety else panda_type, VALUE_COLOR))

    free_space = device_state.freeSpacePercent
    temp = device_state.maxTempC
    items.append((f"{free_space:.0f}% free", VALUE_COLOR if free_space > LOW_SPACE_PERCENT else WARN_COLOR))
    items.append((f"{temp:.0f} °C", VALUE_COLOR if temp < WARM_TEMP_C else WARN_COLOR))
    items.append((str(device_state.networkType), VALUE_COLOR))
    items.append((f"{self._route_count} drives", VALUE_COLOR))

    # a bar too narrow for everything drops from the right, so anything wrong goes to the left
    # of everything that is fine. nothing is ever silently dropped for being a problem.
    items.sort(key=lambda item: item[1] is not WARN_COLOR)
    return items

  def _render(self, rect: rl.Rectangle) -> None:
    x = rect.x
    right = rect.x + rect.width
    separator_width = measure_text_cached(self._font_medium, SEPARATOR, FONT_SIZE).x

    for index, (text, color) in enumerate(self._items()):
      width = measure_text_cached(self._font_medium, text, FONT_SIZE).x
      lead = 0.0 if index == 0 else ITEM_GAP + separator_width + ITEM_GAP
      if x + lead + width > right:
        break

      if index:
        rl.draw_text_ex(self._font_medium, SEPARATOR, rl.Vector2(x + ITEM_GAP, self._text_y(rect)),
                        FONT_SIZE, 0, SEPARATOR_COLOR)
        x += lead

      rl.draw_text_ex(self._font_medium, text, rl.Vector2(x, self._text_y(rect)), FONT_SIZE, 0, color)
      x += width

  def _text_y(self, rect: rl.Rectangle) -> float:
    return rect.y + (rect.height - FONT_SIZE) / 2
