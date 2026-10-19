# Wild Flame for Home Assistant

Local control of **Wild Flame Smart Fire** bio-ethanol burners (tested with the Smart Fire A6, 80 cm) from
Home Assistant. No cloud: Home Assistant talks directly to the burner over the burner's own Wi-Fi.

> **Unofficial.** This project is not made, endorsed or supported by Wild Flame or AG Solutions.
> It controls a device that produces open flames. **Use it at your own risk**, never leave a burning
> fireplace unattended, and follow the manufacturer's safety instructions. The burner's own safety
> system stays in charge; this integration only sends the same commands as the official app.

🇳🇱 [Nederlandse handleiding](docs/README.nl.md)

## Features

| Entity | What it does |
|---|---|
| `switch.<name>` | Turn the burner on or off |
| `number.<name>_flame_level` | Flame level 1–10 (unavailable unless the burner is burning) |
| `sensor.<name>_status` | Off / Warming up / Burning / Cooling down / Unknown phase, with a `since` attribute |
| `sensor.<name>_last_switched_on` | When the burner was last switched on (kept after it goes off) |
| `sensor.<name>_fuel_level` | Fuel level in % (steps of 10%) |
| `binary_sensor.<name>_fuel_low` | On at 10% fuel or less |
| `sensor.<name>_room_temperature` | Room temperature in °C |
| `sensor.<name>_humidity` | Humidity in % |
| `lock.<name>_child_lock` | Child lock on the burner: lock or unlock it |
| `number.<name>_auto_off_after` | Switch the burner off after this many hours (0 = never; configuration) |
| `sensor.<name>_phase_code` | Raw phase code (diagnostic) |

Entity names follow your Home Assistant language (English and Dutch included).

### Built-in safety
The burner only understands *toggle* and *step* commands: the same command switches it on **and** off.
The integration therefore always reads the current status first and only sends a command when needed:
- switching on is refused while the burner is cooling down or the child lock is active;
- switching on is also refused when the burner reports a phase code the integration does not know
  (possibly an error); the code is logged so it can be added;
- after an on/off or child lock command no second one is sent for 30 seconds, until the burner reports the
  new state (a second toggle would undo the first);
- the optional auto-off time switches the burner off after it has been on that long, also when no
  automation is set up;
- the flame level changes in single steps one second apart, and only while the burner is burning.

## Requirements

The burner only offers its own Wi-Fi network (`WILDFLAME…`, address `192.168.4.1`); it does not join your
home network. Home Assistant needs a second network connection to that Wi-Fi, for example:

- **A Raspberry Pi running Home Assistant OS on Ethernet** (tested): use its built-in Wi-Fi for the burner.
- Any host with a spare Wi-Fi adapter.

### Connecting Home Assistant OS to the burner's Wi-Fi
1. **Settings → System → Network → Configure network interfaces → WLAN0.**
2. Search for networks, pick `WILDFLAME…`, security **WPA-PSK**, and enter the burner's Wi-Fi password.
3. IPv4: **Automatic**.
4. Leave the Ethernet interface unchanged.

Ethernet stays your default route to the internet; Wi-Fi is only used for `192.168.4.x`.
The burner's Wi-Fi accepts only a few clients; your phone does not need to stay connected to it.

## Installation

### HACS (recommended)
1. HACS → ⋮ → **Custom repositories** → add `https://github.com/stfnw-coding/wildflame-ha`, category **Integration**.
2. Install **Wild Flame** and restart Home Assistant.

### Manual
Copy `custom_components/wildflame` to `/config/custom_components/wildflame` and restart Home Assistant.

## Setup
**Settings → Devices & services → Add integration → Wild Flame.** Keep the IP address at `192.168.4.1`.
The integration checks that the burner is reachable before it is added.

## What to expect
| Phase | LED | Status | Notes |
|---|---|---|---|
| Ready | off | Off | Can be switched on |
| Warming up | green, blinking | Warming up | About 7 minutes. Flames appear before the end, but the flame level cannot be changed yet |
| Burning | – | Burning | Starts at level 5, adjustable 1–10 |
| Cooling down | red, blinking | Cooling down | Can take over an hour. Cannot be switched on or refilled |

An automation on `sensor.<name>_status` changing from `cooling` to `off` is a good way to get notified
when the burner can be used or refilled again.

## How it works
See [docs/PROTOCOL.md](docs/PROTOCOL.md) for the local HTTP protocol.

## Contributing
Own a different Wild Flame model? Issues with your burner's status line (from
`http://192.168.4.1/info.php`) and what you see on the burner are very welcome.

```bash
pip install -r requirements_test.txt
pytest
```
The tests use a fake burner (`tests/fake_burner.py`) that answers like the real one.

## License
[MIT](LICENSE)
