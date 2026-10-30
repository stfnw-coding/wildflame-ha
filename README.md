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
| `sensor.<name>_status` | Off / Warming up / Burning / Cooling down / Fuel empty / Unknown phase |
| `sensor.<name>_fuel_level` | Fuel level in % (steps of 10%) |
| `sensor.<name>_room_temperature` | Room temperature in °C |
| `sensor.<name>_humidity` | Humidity in % |
| `lock.<name>_child_lock` | Child lock on the burner: lock or unlock it |
| `sensor.<name>_phase_code` | Raw phase code (diagnostic) |
| `sensor.<name>_wi_fi_signal` | Signal strength in % of Home Assistant's Wi-Fi connection to the burner (diagnostic, Home Assistant OS only) |

Entity names follow your Home Assistant language (English and Dutch included).

### Built-in safety
The burner only understands *toggle* and *step* commands: the same command switches it on **and** off.
The integration therefore always reads the current status first and only sends a command when needed:
- switching on is refused while the burner is cooling down, out of fuel or the child lock is active;
- switching on is also refused when the burner reports a phase code the integration does not know
  (possibly an error); the code is logged so it can be added;
- after an on/off or child lock command no second one is sent for 30 seconds, until the burner reports the
  new state (a second toggle would undo the first);
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
**Settings → Devices & services → Add integration → Wild Flame.**

| Field | Description |
|---|---|
| IP address | Address of the burner on its own Wi-Fi. Keep it at `192.168.4.1` unless you changed it. |
| Wi-Fi password (optional) | Password of the burner's Wi-Fi. Home Assistant OS only: lets the integration reconnect Home Assistant to that Wi-Fi when the connection drops and is not restored (see Troubleshooting). |

The integration checks that the burner is reachable before it is added. The device is called *Wild Flame*;
rename it (for example to "Fireplace") on the device page and let Home Assistant rename the entity IDs with it.

Did the address change, or do you want to add or remove the Wi-Fi password? Use **⋮ → Reconfigure** on the
integration entry; there is no need to remove it.

## What to expect
| Phase | LED | Status | Notes |
|---|---|---|---|
| Ready | off | Off | Can be switched on |
| Warming up | green, blinking | Warming up | About 7 minutes. Flames appear before the end, but the flame level cannot be changed yet |
| Burning | – | Burning | Starts at level 5, adjustable 1–10 |
| Cooling down | red, blinking | Cooling down | Can take over an hour. Cannot be switched on or refilled |
| Out of fuel | not recorded yet | Fuel empty | After the tank runs empty: the burner switches itself off, cools down and then reports this. Refill before switching on |

## Examples
- Get notified when the burner can be used or refilled again: trigger on `sensor.<name>_status` changing from
  *Cooling down* to *Off* or *Fuel empty*.
- Get a reminder to refill: numeric state trigger on `sensor.<name>_fuel_level` going below 20 (so at 10% or less).
- Make sure the burner never burns all night: an automation that turns off `switch.<name>` when it has been
  on for, for example, 4 hours (state trigger with *for*). Note that Home Assistant restarts this timer when it
  restarts itself.
- See how long the burner has been warming up or cooling down: the *last changed* time of
  `sensor.<name>_status`, shown in its dialog and history.
- See when the burner was switched on and off: the history and logbook of `switch.<name>`.
- Switch the burner off when everybody leaves home: an automation on your presence detection that turns off
  `switch.<name>`.

## Data updates
Home Assistant asks the burner for its status every 5 seconds, and right after every command. Changes made on
the burner itself or with the official app therefore show up within a few seconds. The Wi-Fi signal comes from
Home Assistant OS, once a minute; it is unknown while the Wi-Fi is not connected.

## Known limitations
- The burner only offers its own Wi-Fi; Home Assistant needs a (second) Wi-Fi connection to it (see Requirements).
- The burner only understands toggle and step commands, so commands are refused while a previous on/off or
  child lock command is still being processed.
- The flame level can only be changed while the burner is burning, not while it warms up.
- The fuel level comes in steps of 10%.
- On the tested Smart Fire A6, room temperature and humidity always read 20 °C and 45%, also while burning; the
  official app shows the same values. If yours never change either, disable these two entities.
- Only the Smart Fire A6 has been tested. Other Smart Fire models probably work the same; please report it.

## Troubleshooting
- **"Cannot reach the burner" during setup, or all entities unavailable**: check that Home Assistant is still
  connected to the `WILDFLAME…` Wi-Fi (Settings → System → Network). The burner accepts only a few Wi-Fi
  clients; disconnecting a phone or tablet from it can help.
- **Worked fine, then suddenly unavailable and it stays that way**: if the burner's Wi-Fi drops briefly,
  Home Assistant OS may treat the failed reconnect as a wrong password and stop trying. WLAN0 then has no
  `192.168.4.x` address. Open WLAN0 under Settings → System → Network, enter the burner's Wi-Fi password again
  and save; the integration reconnects by itself within a few minutes.
  With the Wi-Fi password filled in (Setup), the integration does this for you: it checks the Wi-Fi interface
  every minute, also while the integration itself cannot start because the burner is unreachable. When the
  interface has been down for a minute and the burner's network is on the air, it applies the Wi-Fi settings
  again (WPA-PSK, IPv4 automatic) and sets the integration up again right away. The log then shows
  "Home Assistant lost its Wi-Fi connection to the burner". The burner often turns Home Assistant away for a
  while and lets it in a little later, so a reconnect that fails is tried again every 2 minutes; after 10
  tries (a wrong password, say) only every 30 minutes. Each try adds a "Supervisor wlan0" connection profile
  in Home Assistant OS; they do no harm.
- **Unavailable while WLAN0 is connected, with an address and a signal**: the link can get stuck this way too,
  for example after heavy network traffic on the Home Assistant host; reconnecting the Wi-Fi brings the burner
  back. With the Wi-Fi password filled in, the integration does this for you as well: when the burner has not
  answered for 3 minutes on a connected interface, it applies the Wi-Fi settings again, with the same retries
  as above. The log then shows "the burner has not answered for 3 minutes; reconnecting". Short gaps of a
  minute or so, which the burner recovers from by itself, are left alone.
- **"Unknown phase"**: the burner reports a phase code the integration does not know yet, possibly an error.
  Switching on is blocked. Please open an issue with the code and what the burner shows.
- **The Wi-Fi keeps dropping**: look at the history of the Wi-Fi signal sensor. A low signal before each drop
  points at the distance or a wall between Home Assistant and the burner.
- When you report a problem, attach the diagnostics: on the device page, **⋮ → Download diagnostics**.

## Removal
1. **Settings → Devices & services → Wild Flame → ⋮ → Delete.**
2. Installed with HACS? Remove **Wild Flame** in HACS as well and restart Home Assistant.

## How it works
See [docs/PROTOCOL.md](docs/PROTOCOL.md) for the local HTTP protocol.

## Contributing
Own a different Wild Flame model? Issues with your burner's status line (from
`http://192.168.4.1/info.php`) and what you see on the burner are very welcome.

```bash
pip install -r requirements_test.txt
mypy
pytest
```
The tests use a fake burner (`tests/fake_burner.py`) that answers like the real one.

## License
[MIT](LICENSE)
