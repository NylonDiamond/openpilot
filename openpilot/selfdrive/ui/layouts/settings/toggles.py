from openpilot.cereal import log
from openpilot.common.params import Params, UnknownKeyName
from openpilot.system.ui.widgets import Widget
from openpilot.system.ui.widgets.list_view import multiple_button_item, toggle_item
from openpilot.system.ui.widgets.scroller_tici import Scroller
from openpilot.system.ui.widgets.confirm_dialog import ConfirmDialog
from openpilot.system.ui.lib.application import gui_app
from openpilot.system.ui.lib.multilang import tr, tr_noop
from openpilot.system.ui.widgets import DialogResult
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.selfdrive.controls.lib.blinker_pause import ANY_SPEED_MPH, BLINKER_PAUSE_SPEEDS_MPH
from openpilot.selfdrive.controls.lib.lane_position import LANE_POSITION_OFFSETS_CM

PERSONALITY_TO_INT = log.LongitudinalPersonality.schema.enumerants

# seconds to wait before starting a lane change without a nudge, 0 keeps the nudge required
AUTO_LANE_CHANGE_TIMERS = (0, 1, 2, 3)

# seconds to wait after a turn signal cancels before steering comes back
BLINKER_PAUSE_DELAYS = (0, 1, 2, 3)

# the speeds in BLINKER_PAUSE_SPEEDS_MPH as they read on the buttons
BLINKER_PAUSE_SPEED_LABELS = ("Off", "20 mph", "40 mph", "Any")

# how early to warn about an upcoming curve, 0 is off. the levels index a table of lateral
# acceleration thresholds in curve_advisory.py rather than meaning anything on their own
CURVE_ADVISORY_LEVELS = (0, 1, 2, 3)

# onroad display settings that reclaim parts of the UI the stock build only uses to report
# longitudinal state. nothing for them to do on a car openpilot drives end to end.
LATERAL_ONLY_DISPLAY_TOGGLES = ("ShowLeadIndicator", "EngagementPathColor", "HideExperimentalButton")

# Description constants
DESCRIPTIONS = {
  "OpenpilotEnabledToggle": tr_noop(
    "Use the openpilot system for adaptive cruise control and lane keep driver assistance. " +
    "Your attention is required at all times to use this feature."
  ),
  "DisengageOnAccelerator": tr_noop("When enabled, pressing the accelerator pedal will disengage openpilot."),
  "LongitudinalPersonality": tr_noop(
    "Standard is recommended. In aggressive mode, openpilot will follow lead cars closer and be more aggressive with the gas and brake. " +
    "In relaxed mode openpilot will stay further away from lead cars. On supported cars, you can cycle through these personalities with " +
    "your steering wheel distance button."
  ),
  "IsLdwEnabled": tr_noop(
    "Receive alerts to steer back into the lane when your vehicle drifts over a detected lane line " +
    "without a turn signal activated while driving over 31 mph (50 km/h)."
  ),
  "AutoLaneChangeTimer": tr_noop(
    "Nudge requires you to steer towards the turn signal before openpilot will change lanes. " +
    "Choosing a delay lets openpilot start the lane change on its own after that long, as long as the blind spot is clear. " +
    "The blind spot monitor and the 20 mph minimum speed still apply, and steering towards the signal always starts the change immediately."
  ),
  "BlinkerPauseSpeed": tr_noop(
    "openpilot holds the lane straight through a turn signal, so every junction and driveway is a fight with the wheel. " +
    "This hands steering back for as long as the signal is on, below the speed you pick. " +
    "At 20 mph nothing else changes, because openpilot would not offer a lane change down there anyway. " +
    "Above that a turn signal could just as easily mean a lane change, and openpilot cannot tell the two apart, " +
    "so the higher settings cover turns off faster roads and give up the automatic lane change below the same speed. " +
    "Once it starts, steering stays off until the signal cancels, so a signal left on leaves steering off."
  ),
  "BlinkerPauseDelay": tr_noop(
    "The shortest time to wait after the turn signal cancels before steering comes back. " +
    "The signal cancels as the wheel returns to center, which is the middle of a turn rather than the end of it, " +
    "so steering also waits until the wheel is close to where openpilot would be holding it. " +
    "Whichever of the two takes longer wins, up to a few seconds."
  ),
  "CurveAdvisory": tr_noop(
    "Show a warning when the speed you are carrying into an upcoming curve is high. " +
    "EyeSight holds its set speed through a bend, so nothing in the car says anything about this today. " +
    "The warning is silent and openpilot cannot slow this car, so acting on it is entirely up to you. " +
    "Late warns only about the sharpest curves, Early warns about gentler ones too."
  ),
  "LanePosition": tr_noop(
    "Where in the lane openpilot places the car. Centered is how it drives today. " +
    "The other positions move it toward one side, which helps on a narrow lane with a truck alongside, " +
    "or on a road where the crown or the camber puts you closer to one line than you would like. " +
    "It eases across over about half a second when steering engages, and returns to centered when it disengages."
  ),
  "MadsEnabled": tr_noop(
    "Keep steering active when adaptive cruise drops out. Steering starts the first time you engage cruise, " +
    "then stays on through brake presses and cancels until you switch EyeSight off with the button on the steering wheel. " +
    "Without this, anything that stops cruise also stops steering."
  ),
  "MadsMainSwitch": tr_noop(
    "Requires Keep Steering On Without Cruise. Switching cruise on is enough to start steering, with no set speed and no need to engage cruise. " +
    "EyeSight main is already on when the car starts, so tap the cruise button off and back on once openpilot is up. " +
    "Switching cruise off still stops steering."
  ),
  "ReverseGearDebounce": tr_noop(
    "Shifting into park runs the lever through reverse on the way, and openpilot acts on that the instant it sees it, " +
    "so a take control alert fires while steering is still on. This makes it wait a tenth of a second first. " +
    "Genuinely selecting reverse is detected that much later."
  ),
  "ShowLeadIndicator": tr_noop(
    "Mark the vehicle ahead on the driving screen. This car has no radar, so the marker follows the lead the driving model sees, " +
    "which is the closest available read on what the stock system is reacting to. " +
    "openpilot normally hides it unless it controls the gas and brake itself."
  ),
  "EngagementPathColor": tr_noop(
    "Turn the driving path green while openpilot is steering and white while it is not. " +
    "The path color normally tracks openpilot's use of the throttle, and the stock cruise owns that on this car, " +
    "so without this the path stays green whether or not anything is steering."
  ),
  "HideExperimentalButton": tr_noop(
    "Remove the steering wheel button from the top right of the driving screen. " +
    "Experimental mode needs openpilot longitudinal control, which this car does not have, " +
    "so the button cannot do anything and only blocks taps in that corner."
  ),
  "WideCameraLowSpeed": tr_noop(
    "Switch the driving screen to the wide angle camera below 22 mph (36 km/h), which shows far more of a junction " +
    "than the narrow camera can. It switches back above 34 mph (54 km/h). " +
    "This only changes the picture on screen. The driving model reads both cameras at every speed either way. " +
    "openpilot normally does this only in experimental mode, which this car cannot use."
  ),
  "AlwaysOnDM": tr_noop("Enable driver monitoring even when openpilot is not engaged."),
  'RecordFront': tr_noop("Upload data from the cabin camera and help improve the driver monitoring algorithm."),
  "IsMetric": tr_noop("Display speed in km/h instead of mph."),
  "RecordAudio": tr_noop("Record and store microphone audio while driving. The audio will be included in the dashcam video in comma connect."),
}


class TogglesLayout(Widget):
  def __init__(self):
    super().__init__()
    self._params = Params()
    self._is_release = self._params.get_bool("IsReleaseBranch")

    # param, title, desc, icon, needs_restart
    self._toggle_defs = {
      "OpenpilotEnabledToggle": (
        lambda: tr("Enable openpilot"),
        DESCRIPTIONS["OpenpilotEnabledToggle"],
        "chffr_wheel.png",
        True,
      ),
      "ExperimentalMode": (
        lambda: tr("Experimental Mode"),
        "",
        "experimental_white.png",
        False,
      ),
      "DisengageOnAccelerator": (
        lambda: tr("Disengage on Accelerator Pedal"),
        DESCRIPTIONS["DisengageOnAccelerator"],
        "disengage_on_accelerator.png",
        False,
      ),
      "MadsEnabled": (
        lambda: tr("Keep Steering On Without Cruise"),
        DESCRIPTIONS["MadsEnabled"],
        "chffr_wheel.png",
        # changes what the panda will allow, so it can only be applied at car init
        True,
      ),
      "MadsMainSwitch": (
        lambda: tr("Steer With The Cruise Switch"),
        DESCRIPTIONS["MadsMainSwitch"],
        "chffr_wheel.png",
        # changes what the panda will allow, so it can only be applied at car init
        True,
      ),
      "ReverseGearDebounce": (
        lambda: tr("Ignore Reverse While Shifting"),
        DESCRIPTIONS["ReverseGearDebounce"],
        "warning.png",
        False,
      ),
      "IsLdwEnabled": (
        lambda: tr("Enable Lane Departure Warnings"),
        DESCRIPTIONS["IsLdwEnabled"],
        "warning.png",
        False,
      ),
      "ShowLeadIndicator": (
        lambda: tr("Show Lead Car Marker"),
        DESCRIPTIONS["ShowLeadIndicator"],
        "triangle.png",
        False,
      ),
      "EngagementPathColor": (
        lambda: tr("Color Path By Steering"),
        DESCRIPTIONS["EngagementPathColor"],
        "road.png",
        False,
      ),
      "HideExperimentalButton": (
        lambda: tr("Hide Experimental Mode Button"),
        DESCRIPTIONS["HideExperimentalButton"],
        "experimental_grey.png",
        False,
      ),
      "WideCameraLowSpeed": (
        lambda: tr("Wide Camera At Low Speed"),
        DESCRIPTIONS["WideCameraLowSpeed"],
        "road.png",
        False,
      ),
      "AlwaysOnDM": (
        lambda: tr("Always-On Driver Monitoring"),
        DESCRIPTIONS["AlwaysOnDM"],
        "monitoring.png",
        False,
      ),
      "RecordFront": (
        lambda: tr("Record and Upload Cabin Camera"),
        DESCRIPTIONS["RecordFront"],
        "monitoring.png",
        True,
      ),
      "RecordAudio": (
        lambda: tr("Record and Upload Microphone Audio"),
        DESCRIPTIONS["RecordAudio"],
        "microphone.png",
        True,
      ),
      "IsMetric": (
        lambda: tr("Use Metric System"),
        DESCRIPTIONS["IsMetric"],
        "metric.png",
        False,
      ),
    }

    self._long_personality_setting = multiple_button_item(
      lambda: tr("Driving Personality"),
      lambda: tr(DESCRIPTIONS["LongitudinalPersonality"]),
      buttons=[lambda: tr("Aggressive"), lambda: tr("Standard"), lambda: tr("Relaxed")],
      button_width=255,
      callback=self._set_longitudinal_personality,
      selected_index=self._params.get("LongitudinalPersonality", return_default=True),
      icon="speed_limit.png"
    )

    auto_lane_change_timer = self._params.get("AutoLaneChangeTimer", return_default=True)
    self._auto_lane_change_setting = multiple_button_item(
      lambda: tr("Automatic Lane Change"),
      lambda: tr(DESCRIPTIONS["AutoLaneChangeTimer"]),
      buttons=[lambda: tr("Nudge"), "1s", "2s", "3s"],
      button_width=200,
      callback=self._set_auto_lane_change_timer,
      selected_index=AUTO_LANE_CHANGE_TIMERS.index(auto_lane_change_timer) if auto_lane_change_timer in AUTO_LANE_CHANGE_TIMERS else 0,
      icon="road.png",
    )

    blinker_pause_speed = self._params.get("BlinkerPauseSpeed", return_default=True)
    self._blinker_pause_setting = multiple_button_item(
      lambda: tr("Pause Steering On Turn Signal"),
      lambda: tr(DESCRIPTIONS["BlinkerPauseSpeed"]),
      buttons=[lambda label=label: tr(label) for label in BLINKER_PAUSE_SPEED_LABELS],
      button_width=200,
      callback=self._set_blinker_pause_speed,
      selected_index=BLINKER_PAUSE_SPEEDS_MPH.index(blinker_pause_speed) if blinker_pause_speed in BLINKER_PAUSE_SPEEDS_MPH else 1,
      icon="chffr_wheel.png",
    )

    blinker_pause_delay = self._params.get("BlinkerPauseDelay", return_default=True)
    self._blinker_pause_delay_setting = multiple_button_item(
      lambda: tr("Resume Steering After"),
      lambda: tr(DESCRIPTIONS["BlinkerPauseDelay"]),
      buttons=[lambda: tr("Now"), "1s", "2s", "3s"],
      button_width=200,
      callback=self._set_blinker_pause_delay,
      selected_index=BLINKER_PAUSE_DELAYS.index(blinker_pause_delay) if blinker_pause_delay in BLINKER_PAUSE_DELAYS else 1,
      icon="chffr_wheel.png",
    )

    curve_advisory = self._params.get("CurveAdvisory", return_default=True)
    self._curve_advisory_setting = multiple_button_item(
      lambda: tr("Curve Speed Warning"),
      lambda: tr(DESCRIPTIONS["CurveAdvisory"]),
      buttons=[lambda: tr("Off"), lambda: tr("Late"), lambda: tr("Normal"), lambda: tr("Early")],
      button_width=200,
      callback=self._set_curve_advisory,
      selected_index=CURVE_ADVISORY_LEVELS.index(curve_advisory) if curve_advisory in CURVE_ADVISORY_LEVELS else 0,
      icon="speed_limit.png",
    )

    lane_position = self._params.get("LanePosition", return_default=True)
    self._lane_position_setting = multiple_button_item(
      lambda: tr("Lane Position"),
      lambda: tr(DESCRIPTIONS["LanePosition"]),
      buttons=[lambda: tr("Far Left"), lambda: tr("Left"), lambda: tr("Center"), lambda: tr("Right"), lambda: tr("Far Right")],
      button_width=160,
      callback=self._set_lane_position,
      selected_index=LANE_POSITION_OFFSETS_CM.index(lane_position) if lane_position in LANE_POSITION_OFFSETS_CM else 2,
      icon="road.png",
    )

    self._toggles = {}
    self._locked_toggles = set()
    for param, (title, desc, icon, needs_restart) in self._toggle_defs.items():
      toggle = toggle_item(
        title,
        desc,
        self._params.get_bool(param),
        callback=lambda state, p=param: self._toggle_callback(state, p),
        icon=icon,
      )

      try:
        locked = self._params.get_bool(param + "Lock")
      except UnknownKeyName:
        locked = False
      toggle.action_item.set_enabled(not locked)

      # Make description callable for live translation
      additional_desc = ""
      if needs_restart and not locked:
        additional_desc = tr("Changing this setting will restart openpilot if the car is powered on.")
      toggle.set_description(lambda og_desc=toggle.description, add_desc=additional_desc: tr(og_desc) + (" " + tr(add_desc) if add_desc else ""))

      # track for engaged state updates
      if locked:
        self._locked_toggles.add(param)

      self._toggles[param] = toggle

      # insert longitudinal personality after NDOG toggle
      if param == "DisengageOnAccelerator":
        self._toggles["LongitudinalPersonality"] = self._long_personality_setting

      # keep the curve warning with the other thing that only warns the driver, and group
      # automatic lane change with the other lane related setting
      if param == "IsLdwEnabled":
        self._toggles["CurveAdvisory"] = self._curve_advisory_setting
        self._toggles["LanePosition"] = self._lane_position_setting
        self._toggles["AutoLaneChangeTimer"] = self._auto_lane_change_setting
        # the other two settings a turn signal reaches, and the delay only means anything with
        # the pause on, so keep the three of them together and in that order
        self._toggles["BlinkerPauseSpeed"] = self._blinker_pause_setting
        self._toggles["BlinkerPauseDelay"] = self._blinker_pause_delay_setting

    self._update_experimental_mode_icon()
    self._scroller = Scroller(list(self._toggles.values()), line_separator=True, spacing=0)

    ui_state.add_engaged_transition_callback(self._update_toggles)

  def _update_state(self):
    if ui_state.sm.updated["selfdriveState"]:
      personality = PERSONALITY_TO_INT[ui_state.sm["selfdriveState"].personality]
      if personality != ui_state.personality and ui_state.started:
        self._long_personality_setting.action_item.set_selected_button(personality)
      ui_state.personality = personality

  def show_event(self):
    super().show_event()
    self._scroller.show_event()
    self._update_toggles()

  def _update_toggles(self):
    ui_state.update_params()

    e2e_description = tr(
      "openpilot defaults to driving in chill mode. Experimental mode enables alpha-level features that aren't ready for chill mode. " +
      "Experimental features are listed below:<br>" +
      "<h4>End-to-End Longitudinal Control</h4><br>" +
      "Let the driving model control the gas and brakes. openpilot will drive as it thinks a human would, including stopping for red lights and stop signs. " +
      "Since the driving model decides the speed to drive, the set speed will only act as an upper bound. This is an alpha quality feature; " +
      "mistakes should be expected.<br>" +
      "<h4>New Driving Visualization</h4><br>" +
      "The driving visualization will transition to the road-facing wide-angle camera at low speeds to better show some turns. " +
      "The Experimental mode logo will also be shown in the top right corner."
    )

    if ui_state.CP is not None:
      if ui_state.has_longitudinal_control:
        self._toggles["ExperimentalMode"].action_item.set_enabled(True)
        self._toggles["ExperimentalMode"].set_description(e2e_description)
        self._long_personality_setting.action_item.set_enabled(True)
      else:
        # no long for now
        self._toggles["ExperimentalMode"].action_item.set_enabled(False)
        self._toggles["ExperimentalMode"].action_item.set_state(False)
        self._long_personality_setting.action_item.set_enabled(False)
        self._params.remove("ExperimentalMode")

        unavailable = tr("Experimental mode is currently unavailable on this car since the car's stock ACC is used for longitudinal control.")

        long_desc = unavailable + " " + tr("openpilot longitudinal control may come in a future update.")
        if ui_state.CP.alphaLongitudinalAvailable:
          if self._is_release:
            long_desc = unavailable + " " + tr("An alpha version of openpilot longitudinal control can be tested, along with " +
                                               "Experimental mode, on non-release branches.")
          else:
            long_desc = tr("Enable the openpilot longitudinal control (alpha) toggle to allow Experimental mode.")

        self._toggles["ExperimentalMode"].set_description("<b>" + long_desc + "</b><br><br>" + e2e_description)

      for param in LATERAL_ONLY_DISPLAY_TOGGLES:
        self._toggles[param].action_item.set_enabled(not ui_state.has_longitudinal_control)
    else:
      self._toggles["ExperimentalMode"].set_description(e2e_description)

    self._update_experimental_mode_icon()

    # TODO: make a param control list item so we don't need to manage internal state as much here
    # refresh toggles from params to mirror external changes
    for param in self._toggle_defs:
      self._toggles[param].action_item.set_state(self._params.get_bool(param))

    self._update_blinker_pause_dependents(self._params.get("BlinkerPauseSpeed", return_default=True))

    # these toggles need restart, block while engaged
    for toggle_def in self._toggle_defs:
      if self._toggle_defs[toggle_def][3] and toggle_def not in self._locked_toggles:
        self._toggles[toggle_def].action_item.set_enabled(not ui_state.engaged)

  def _render(self, rect):
    self._scroller.render(rect)

  def _update_experimental_mode_icon(self):
    icon = "experimental.png" if self._toggles["ExperimentalMode"].action_item.get_state() else "experimental_white.png"
    self._toggles["ExperimentalMode"].set_icon(icon)

  def _handle_experimental_mode_toggle(self, state: bool):
    confirmed = self._params.get_bool("ExperimentalModeConfirmed")
    if state and not confirmed:
      def confirm_callback(result: DialogResult):
        if result == DialogResult.CONFIRM:
          self._params.put_bool("ExperimentalMode", True, block=True)
          self._params.put_bool("ExperimentalModeConfirmed", True, block=True)
        else:
          self._toggles["ExperimentalMode"].action_item.set_state(False)
        self._update_experimental_mode_icon()

      # show confirmation dialog
      content = (f"<h1>{self._toggles['ExperimentalMode'].title}</h1><br>" +
                 f"<p>{self._toggles['ExperimentalMode'].description}</p>")
      dlg = ConfirmDialog(content, tr("Enable"), rich=True, callback=confirm_callback)
      gui_app.push_widget(dlg)
    else:
      self._update_experimental_mode_icon()
      self._params.put_bool("ExperimentalMode", state, block=True)

  def _toggle_callback(self, state: bool, param: str):
    if param == "ExperimentalMode":
      self._handle_experimental_mode_toggle(state)
      return

    self._params.put_bool(param, state, block=True)
    if self._toggle_defs[param][3]:
      self._params.put_bool("OnroadCycleRequested", True, block=True)

  def _set_auto_lane_change_timer(self, button_index: int):
    self._params.put("AutoLaneChangeTimer", AUTO_LANE_CHANGE_TIMERS[button_index], block=True)

  def _update_blinker_pause_dependents(self, speed_mph: int):
    # the delay says nothing with the pause off, and a pause with no speed limit takes every
    # signal before the lane change assist can see one
    self._blinker_pause_delay_setting.action_item.set_enabled(speed_mph > 0)
    self._auto_lane_change_setting.action_item.set_enabled(speed_mph < ANY_SPEED_MPH)

  def _set_blinker_pause_speed(self, button_index: int):
    speed_mph = BLINKER_PAUSE_SPEEDS_MPH[button_index]
    self._params.put("BlinkerPauseSpeed", speed_mph, block=True)
    # _update_toggles only runs on show and on engaged transitions, so grey the others here too
    self._update_blinker_pause_dependents(speed_mph)

  def _set_blinker_pause_delay(self, button_index: int):
    self._params.put("BlinkerPauseDelay", BLINKER_PAUSE_DELAYS[button_index], block=True)

  def _set_lane_position(self, button_index: int):
    self._params.put("LanePosition", LANE_POSITION_OFFSETS_CM[button_index], block=True)

  def _set_curve_advisory(self, button_index: int):
    self._params.put("CurveAdvisory", CURVE_ADVISORY_LEVELS[button_index], block=True)

  def _set_longitudinal_personality(self, button_index: int):
    self._params.put("LongitudinalPersonality", button_index, block=True)
