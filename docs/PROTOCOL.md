# Wild Flame local protocol

Observed on a Smart Fire A6 (80 cm) with the iOS app "Wild Flame" 1.1.0, October 2026.

## Network
- The burner runs a Wi-Fi access point named `WILDFLAME…` and hands out addresses in `192.168.4.0/24`.
- It serves plain HTTP on `192.168.4.1:80`. There is no authentication and no session.
- Every response closes the connection; there is no `Content-Length` header.

## Status: `GET /info.php`
```
 usart1=2, usart2=0, usart3=5, usart4=45, usart5=20, usart6=0, usart7=1
```
`text/html`, one line, starting with a space. The official app polls it once per second.

| Field | Meaning |
|---|---|
| `usart1` | Fuel level in tenths (`2` = 20%) |
| `usart2` | Phase code, matches the status LED: `6` ready (LED off), `10` warming up (green blinking), `0` burning, `1` cooling down (red blinking), `7` out of fuel (LED not recorded yet) |
| `usart3` | Flame level `1`–`10`; `0` while not burning or still warming up |
| `usart4` | Humidity, % (see note) |
| `usart5` | Room temperature, °C (see note) |
| `usart6` | Child lock: `0` off, otherwise on |
| `usart7` | Power: `0` off, otherwise on |

## Commands: `POST /info.php`
Body `on=<code>`, `Content-Type: application/x-www-form-urlencoded`.

| Code | Action |
|---|---|
| `82534KL` | Power **toggle** (the same code switches on and off) |
| `25896CH` | Flame level +1 |
| `32768PN` | Flame level −1 |
| `36548NP` | Child lock **toggle** |

There is no command to set an absolute power state or flame level. Read the status first.

## Observed sequence
| Time | Event | Status |
|---|---|---|
| 0:00 | `82534KL` sent | `usart7=1`, `usart2=10`, `usart3=0` |
| ~5:00 | Flames visible | unchanged |
| ~6:40 | Ready to adjust | `usart2=0`, `usart3=5` |
| later | `82534KL` sent | `usart7=0`, `usart2=1`, `usart3=0` |
| +~85 min | Cooled down, red LED off | `usart2=6` |

Running out of fuel while burning (2026-10-20): the burner switches itself off and cools down as usual, but ends
in phase `7` instead of `6`.

| Time | Event | Status |
|---|---|---|
| 0:00 | Burning at 10% fuel | `usart1=1`, `usart7=1`, `usart2=0` |
| ~27 min | Tank empty, burner switches off | `usart1=0`, `usart7=0`, `usart2=1`, `usart3=0` |
| +~49 min | Cooled down | `usart1=0`, `usart2=7` |

Note on `usart4` and `usart5`: on the tested Smart Fire A6 they always read `45` and `20`, also while burning
and cooling down, and the official app shows the same fixed values. On this unit they are not real
measurements. Other units or models may report real values; reports are welcome.

Unknown so far: the LED in phase `7`, whether it returns to `6` by itself after refilling, and phase codes for errors or
a blocked burner (e.g. room or fuel below 17 °C).
