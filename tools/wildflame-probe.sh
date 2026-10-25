#!/bin/bash
# Explore the burner's network services with read-only requests. Sends NO commands (no POST, nothing written to
# any port). Run it on a machine connected to the burner's WILDFLAME... Wi-Fi, for example in Home Assistant's
# Terminal app: bash wildflame-probe.sh
# Output goes to the screen and ./wildflame-probe.txt.
#
# Gentle on purpose: a short port list and a pause between requests. The burner's Wi-Fi chip is small, and if it
# hangs, the Wi-Fi drops.

HOST=${1:-192.168.4.1}
OUT=./wildflame-probe.txt
TCP_PORTS=(21 22 23 53 80 81 443 502 1883 2323 5000 8080 8266 8888 9000)
PATHS=(
  / /index.html /index.htm /index.php /info.php /info /status /status.php /state
  /config /config.php /settings /settings.php /setup /setup.php /wifi /wifi.php
  /network /version /about /api /data /data.php /json /log /debug
  /favicon.ico /robots.txt /generate_204 /hotspot-detect.html /does-not-exist-404
)
# Deliberately NOT probed: /reset /restart /reboot /update /ota /firmware /cmd /control /upload. On simple
# firmware a GET to those can already trigger an action.

# Runs a command and kills it after $1 seconds. `timeout` is missing on macOS.
with_timeout() {
  local secs=$1
  shift
  "$@" &
  local pid=$!
  (sleep "$secs" && kill "$pid" 2>/dev/null) &
  local killer=$!
  wait "$pid" 2>/dev/null
  local rc=$?
  kill "$killer" 2>/dev/null
  wait "$killer" 2>/dev/null
  return $rc
}

tcp_connect() { exec 3<>"/dev/tcp/$HOST/$1"; }

# Connects and only listens for 5 s: anything the port says by itself (a banner, or a serial bridge passing on
# data). Bash's own read timeout, so no child process outlives it.
tcp_listen() {
  exec 3<>"/dev/tcp/$HOST/$1" || return
  local end=$((SECONDS + 5)) chunk rc
  while ((SECONDS < end)); do
    chunk=
    IFS= read -r -t 1 -n 200 chunk <&3
    rc=$?
    [ -n "$chunk" ] && printf '%q\n' "$chunk"
    # Above 128: timed out, keep listening; otherwise closed. Bash 3 (macOS) returns 1 for both, so keep going.
    ((rc == 0 || rc > 128 || BASH_VERSINFO[0] < 4)) || break
  done
}

{
  echo "=== $(date) host $HOST"
  echo "=== neighbour (MAC of the burner)"
  ip neigh show "$HOST" 2>/dev/null || arp -n "$HOST" 2>/dev/null
  echo "=== TCP ports"
  open_ports=()
  for p in "${TCP_PORTS[@]}"; do
    if with_timeout 3 bash -c "$(declare -f tcp_connect); HOST=$HOST; tcp_connect $p" 2>/dev/null; then
      echo "open: $p"
      open_ports+=("$p")
    fi
    sleep 0.3
  done
  for p in "${open_ports[@]}"; do
    case $p in 80 | 2323) continue ;; esac  # 2323: on esp-link a connection there resets the microcontroller
    echo
    echo "################ listen 5 s on port $p (nothing sent)"
    with_timeout 8 bash -c "$(declare -f tcp_listen); HOST=$HOST; tcp_listen $p" 2>/dev/null
  done
  for path in "${PATHS[@]}"; do
    echo
    echo "################ GET $path"
    curl -s -m 5 -i "http://$HOST$path" | head -c 1500
    echo
    sleep 0.5
  done
  echo
  echo "################ HEAD /info.php"
  curl -s -m 5 -I "http://$HOST/info.php"
  echo "=== done $(date)"
} 2>&1 | tee "$OUT"

echo "Done: $OUT"
