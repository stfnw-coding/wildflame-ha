"""Constants for the Wild Flame integration."""

from datetime import timedelta

DOMAIN = "wildflame"
MANUFACTURER = "Wild Flame"
MODEL = "Smart Fire A6"

SCAN_INTERVAL = timedelta(seconds=5)

# After a power or child lock toggle, refuse another one until the burner reports the new state
# or this many seconds have passed. A second toggle would undo the first.
POWER_TOGGLE_GUARD_SECONDS = 30

# Pause between single flame steps so the burner registers each one.
FLAME_STEP_DELAY_SECONDS = 1.0

# Fuel level (%) at or below which the "fuel low" problem sensor turns on.
FUEL_LOW_PERCENT = 10
