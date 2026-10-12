#!/usr/bin/env bash
# Runs the AppiumLibrary checks on a booted Android emulator (CI: inside android-emulator-runner).
# Needs appium with the uiautomator2 driver on PATH. The emulator reaches the host as 10.0.2.2.
set -u
cd "$(dirname "$0")"
python -m http.server 8765 --bind 127.0.0.1 --directory pages > "${RESULTS_DIR:-results}-http.log" 2>&1 &
http=$!
appium --port 4723 --allow-insecure "uiautomator2:chromedriver_autodownload" > "${RESULTS_DIR:-results}-appium.log" 2>&1 &
appium=$!
for _ in $(seq 60); do
    curl -sf http://127.0.0.1:4723/status > /dev/null && break
    sleep 1
done
python check.py appium mobileweb
status=$?
kill "$http" "$appium" 2> /dev/null
exit $status
