"""Chimes once when the car you are stopped behind starts to move.

Nothing in this car says this. EyeSight will creep after a lead on its own, but only while its
cruise is engaged and holding, and it says nothing at all when it is not. The gap it leaves is
the one every driver fills by staring at the bumper in front of them.

The lead here comes from the comma's own camera, because this car has no radar interface and
EyeSight's one distance signal saturates at 5 m. That decides the shape of the test below. A
vision lead's absolute speed is a model estimate and it is at its worst at a standstill, which
is exactly where this feature lives, so speed alone would fire at every shimmer. Distance is
the steadier of the two, so departure is measured as the gap opening from its closest point,
with speed kept only as a sanity check on it.
"""

# how slow counts as stopped, for us and for the lead. the lead's is looser because a vision
# lead's speed estimate is noisier than the wheel speeds this car reports for itself.
STOPPED_SPEED = 0.3        # m/s
LEAD_STOPPED_SPEED = 0.8   # m/s

# the lead has to reach this before an opening gap is read as it driving off rather than as the
# distance estimate wandering
LEAD_DEPART_SPEED = 1.2    # m/s

# how far the gap has to open from its closest point
DEPART_DISTANCE = 2.0      # m

# past this it is not the car you are waiting behind, it is scenery
MAX_LEAD_DISTANCE = 30.0   # m

# how long the pair has to sit still before the alert arms. this is what stops it firing on the
# roll up to a queue, where the gap is closing and reopening the whole way in
ARM_TIME = 1.5             # s

# the model's own confidence in the lead. below this the distance is not worth measuring against
MIN_LEAD_PROB = 0.5


class LeadDeparture:
  """Fires a single shot the moment the stopped lead pulls away.

  Deliberately one frame of True rather than a held condition: the alert's own duration decides
  how long it stays up, and a held event would restart that timer every frame and never clear.
  """

  def __init__(self, dt: float):
    # selfdrived's opposite number: the owning process reads the param and sets this
    self.enabled = False

    self._dt = dt
    self._armed_time = 0.0
    self._min_distance: float | None = None
    self._fired = False

  def _reset(self) -> None:
    self._armed_time = 0.0
    self._min_distance = None
    self._fired = False

  def update(self, radar_state, CS) -> bool:
    """True on the one frame the lead is judged to have departed."""
    if not self.enabled:
      self._reset()
      return False

    # moving again is what re-arms this, so the next queue gets its own alert
    if CS.vEgo > STOPPED_SPEED:
      self._reset()
      return False

    lead = radar_state.leadOne
    if not lead.present or lead.modelProb < MIN_LEAD_PROB or lead.dRel > MAX_LEAD_DISTANCE:
      self._reset()
      return False

    distance = lead.dRel
    speed = lead.vLead

    # still settling, or the pair never actually came to rest together
    if self._armed_time < ARM_TIME:
      if speed > LEAD_STOPPED_SPEED:
        self._armed_time = 0.0
        self._min_distance = None
      else:
        self._armed_time += self._dt
        self._min_distance = distance if self._min_distance is None else min(self._min_distance, distance)
      return False

    # armed. track the gap closing too, in case the lead shuffles forward before it goes
    if self._min_distance is None or distance < self._min_distance:
      self._min_distance = distance

    if self._fired:
      return False

    departed = (distance - self._min_distance) > DEPART_DISTANCE and speed > LEAD_DEPART_SPEED
    if departed:
      self._fired = True
    return departed
