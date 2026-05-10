"""Threshold configuration for digital signal detection.

Provides threshold presets (TTL, CMOS, etc.) and a dataclass for per-trace
threshold settings with Schmitt-trigger hysteresis.
"""

from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class ThresholdConfig:
    """Voltage thresholds for converting analog signals to digital logic levels.

    Uses Schmitt-trigger hysteresis: V_low is the falling threshold (1→0),
    V_high is the rising threshold (0→1). The gap prevents glitchy toggling
    on noisy signals.
    """

    v_high: float  # Rising threshold (0→1 transition)
    v_low: float   # Falling threshold (1→0 transition)
    v_undef: float = -0.5  # Voltage for unknown (Z/X) state display
    description: str = ""

    @classmethod
    def from_range(cls, v_min: float, v_max: float, margin: float = 0.2) -> "ThresholdConfig":
        """Auto-compute thresholds from signal voltage range.

        Default: V_low = 20% of range, V_high = 80% of range.
        """
        span = v_max - v_min
        if span <= 0:
            span = 1.0
        return cls(
            v_low=v_min + span * margin,
            v_high=v_min + span * (1.0 - margin),
            description=f"Auto {margin:.0%}/{1-margin:.0%}"
        )


# Preset threshold configurations
PRESETS: Dict[str, ThresholdConfig] = {
    "TTL (5V)": ThresholdConfig(
        v_high=2.0, v_low=0.8,
        description="Standard 5V TTL logic levels"
    ),
    "CMOS 3.3V": ThresholdConfig(
        v_high=2.31, v_low=0.99,
        description="3.3V CMOS (70%/30% Vdd)"
    ),
    "CMOS 5V": ThresholdConfig(
        v_high=3.5, v_low=1.5,
        description="5V CMOS (70%/30% Vdd)"
    ),
    "CMOS 1.8V": ThresholdConfig(
        v_high=1.26, v_low=0.54,
        description="1.8V CMOS (70%/30% Vdd)"
    ),
    "CMOS 1.2V": ThresholdConfig(
        v_high=0.84, v_low=0.36,
        description="1.2V CMOS (70%/30% Vdd)"
    ),
    "LVDS": ThresholdConfig(
        v_high=1.45, v_low=0.95,
        description="LVDS differential (1.2V common-mode, ±250mV)"
    ),
    "Auto (20%/80%)": None,  # Sentinel: computed from signal range at runtime
}


from pqwave.utils.colors import (
    DIGITAL_HIGH_COLOR,
    DIGITAL_LOW_COLOR,
    DIGITAL_UNKNOWN_COLOR,
    DIGITAL_TRANSITION_COLOR,
)
