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
| `usart2` | Phase code, matches the status LED: `6` ready (LED off), `10` warming up (green blinking), `0` burning, `1` cooling down (red blinking) |
| `usart3` | Flame level `1`–`10`; `0` while not burning or still warming up |
| `usart4` | Humidity, % |
| `usart5` | Room temperature, °C |
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

Unknown so far: phase codes for errors or a blocked burner (e.g. room or fuel below 17 °C).
