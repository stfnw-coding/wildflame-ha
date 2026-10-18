#!/bin/bash
# Explore the burner's web server with read-only GET requests.
# Sends NO commands (no POST). Run it while this computer is connected to the burner's WILDFLAME... Wi-Fi.
# Output: ./wildflame-probe.txt

HOST=192.168.4.1
OUT=./wildflame-probe.txt
PATHS=(
  / /index.html /index.htm /index.php /info.php /info /status /status.php /state
  /config /config.php /settings /settings.php /setup /setup.php /wifi /wifi.php
  /network /version /about /api /data /data.php /json /log /debug
  /favicon.ico /robots.txt /generate_204 /hotspot-detect.html
)
# Deliberately NOT probed: /reset /restart /update /ota /firmware /cmd /control —
# on simple firmware a GET to those can already trigger an action.

{
  echo "=== $(date)"
  echo "=== TCP ports"
  for p in 21 22 23 53 80 81 443 502 1883 5000 8080 8266 8888 9000; do
    if nc -z -G 2 "$HOST" "$p" 2>/dev/null; then echo "open: $p"; fi
  done
  for path in "${PATHS[@]}"; do
    echo
    echo "################ GET $path"
    curl -s -m 5 -i "http://$HOST$path" | head -c 3000
    echo
    sleep 0.3
  done
} > "$OUT" 2>&1

echo "Done: $OUT"
