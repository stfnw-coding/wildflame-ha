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

# Optional: the burner's Wi-Fi password, and the interface and network found with it, for Wi-Fi recovery.
CONF_WIFI_INTERFACE = "wifi_interface"
CONF_WIFI_SSID = "wifi_ssid"

# Check this often whether Home Assistant OS gave up on its Wi-Fi connection to the burner.
WIFI_CHECK_INTERVAL_SECONDS = 60
