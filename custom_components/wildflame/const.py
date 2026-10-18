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

# Auto-off: hours the burner may stay on (0 = no limit), and the wait before trying again
# when switching off failed.
AUTO_OFF_MAX_HOURS = 12
AUTO_OFF_RETRY_SECONDS = 120

# Stored "on since" time. It is kept across a Home Assistant restart only if the burner was
# seen burning shortly before; otherwise it may have been switched off and on in between.
STORAGE_VERSION = 1
STORAGE_SAVE_INTERVAL_SECONDS = 60
POWERED_SINCE_MAX_GAP = timedelta(minutes=10)
