"""What the home screen used to spend on advertising: whether this thing is ready to drive.

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

BG_COLOR = rl.Color(51, 51, 51, 255)
SECTION_COLOR = rl.Color(150, 150, 150, 255)
KEY_COLOR = rl.Color(170, 170, 170, 255)
VALUE_COLOR = rl.WHITE
GOOD_COLOR = rl.Color(134, 255, 78, 255)
WARN_COLOR = rl.Color(255, 179, 0, 255)

PADDING = 32
SECTION_FONT_SIZE = 34
ROW_FONT_SIZE = 40
SECTION_GAP = 22
ROW_HEIGHT = 50
SECTION_HEADER_HEIGHT = 46

# the slow reads are params and capnp decodes, neither of which changes between drives
REFRESH_INTERVAL = 10.0

# device is fine well past this, but a comma that has been sitting in the sun is worth noticing
WARM_TEMP_C = 75.0
LOW_SPACE_PERCENT = 10.0

CALIBRATED = log.ExtrinsicsCalibration.Status.calibrated
LAG_ESTIMATED = log.LateralDelay.Status.estimated


def _pretty_fingerprint(fingerprint: str) -> str:
  return fingerprint.replace("_", " ").title()


class StatusBoard(Widget):
  """A read-only summary of the car, the calibration, the panda and the device."""

  def __init__(self):
    super().__init__()
    self._params = Params()
    self._font_medium = gui_app.font(FontWeight.MEDIUM)
    self._font_bold = gui_app.font(FontWeight.BOLD)

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
    pitch_text = f"{abs(pitch):.1f} deg {'down' if pitch > 0 else 'up'}"
    yaw_text = f"{abs(yaw):.1f} deg {'left' if yaw > 0 else 'right'}"
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
    return f"{lag.lateralDelay:.2f} s", True

  def _update_state(self) -> None:
    if time.monotonic() - self._last_refresh >= REFRESH_INTERVAL:
      self.refresh()

  def _sections(self) -> list[tuple[str, list[tuple[str, str, rl.Color]]]]:
    CP = ui_state.CP
    device_state = ui_state.sm["deviceState"]

    car_rows: list[tuple[str, str, rl.Color]] = []
    if CP is None:
      car_rows.append(("", "no car seen yet", WARN_COLOR))
    else:
      car_rows.append(("", _pretty_fingerprint(CP.carFingerprint), VALUE_COLOR))
      car_rows.append(("geometry", f"{CP.wheelbase:.2f} m, ratio {CP.steerRatio:.1f}", VALUE_COLOR))
      car_rows.append(("mass", f"{CP.mass:.0f} kg", VALUE_COLOR))
      car_rows.append(("steering lag", self._steer_lag, GOOD_COLOR if self._steer_lag_ok else WARN_COLOR))

    calib_rows = [("", self._calibration, GOOD_COLOR if self._calibration_ok else WARN_COLOR)]

    panda_rows: list[tuple[str, str, rl.Color]] = []
    panda_type = str(ui_state.panda_type)
    if panda_type == "unknown":
      panda_rows.append(("", "not connected", WARN_COLOR))
    else:
      panda_rows.append(("type", panda_type, VALUE_COLOR))
    if CP is not None and len(CP.safetyConfigs):
      panda_rows.append(("safety", str(CP.safetyConfigs[-1].safetyModel), VALUE_COLOR))

    free_space = device_state.freeSpacePercent
    temp = device_state.maxTempC
    device_rows = [
      ("storage", f"{free_space:.0f}% free", VALUE_COLOR if free_space > LOW_SPACE_PERCENT else WARN_COLOR),
      ("temperature", f"{temp:.0f} C", VALUE_COLOR if temp < WARM_TEMP_C else WARN_COLOR),
      ("network", str(device_state.networkType), VALUE_COLOR),
      ("drives", self._route_count, VALUE_COLOR),
    ]

    return [("CAR", car_rows), ("CALIBRATION", calib_rows), ("PANDA", panda_rows), ("DEVICE", device_rows)]

  @staticmethod
  def _content_height(sections: list[tuple[str, list[tuple[str, str, rl.Color]]]]) -> float:
    height = 2 * PADDING + SECTION_GAP * (len(sections) - 1)
    for _, rows in sections:
      height += SECTION_HEADER_HEIGHT + len(rows) * ROW_HEIGHT
    return height

  def _render(self, rect: rl.Rectangle) -> None:
    sections = self._sections()

    # hug the rows rather than stretching to the column, so the panel does not read as
    # a mostly empty box when the car has fewer things to say
    rect = rl.Rectangle(rect.x, rect.y, rect.width, min(rect.height, self._content_height(sections)))
    rl.draw_rectangle_rounded(rect, 0.03, 20, BG_COLOR)

    x = rect.x + PADDING
    y = rect.y + PADDING
    width = rect.width - 2 * PADDING

    for index, (title, rows) in enumerate(sections):
      rl.draw_text_ex(self._font_bold, title, rl.Vector2(x, y), SECTION_FONT_SIZE, 0, SECTION_COLOR)
      y += SECTION_HEADER_HEIGHT

      for key, value, color in rows:
        if key:
          rl.draw_text_ex(self._font_medium, key, rl.Vector2(x, y), ROW_FONT_SIZE, 0, KEY_COLOR)
        value_width = measure_text_cached(self._font_medium, value, ROW_FONT_SIZE).x
        rl.draw_text_ex(self._font_medium, value, rl.Vector2(x + width - value_width, y), ROW_FONT_SIZE, 0, color)
        y += ROW_HEIGHT

      if index < len(sections) - 1:
        y += SECTION_GAP
