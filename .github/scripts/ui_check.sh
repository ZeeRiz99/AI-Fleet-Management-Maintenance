#!/usr/bin/env bash
# Drives the FleetLog AI app on an emulator like a person would and saves a screenshot after every step.
# Usage: ui_check.sh <app.apk> <out-dir>     (needs adb + python3; used by .github/workflows/android-ui-check.yml)
set -u
APK="$1"; OUT="$2"; PKG=com.zeeriz.fleetai
mkdir -p "$OUT"

log() { echo "[ui-check] $*"; }
shot() { adb exec-out screencap -p > "$OUT/$1.png"; log "screenshot $1"; }
dump() { adb shell uiautomator dump /sdcard/ui.xml >/dev/null 2>&1; adb shell cat /sdcard/ui.xml 2>/dev/null; }

fail() {
  log "FAILED: $*"
  shot zz-failed
  dump > "$OUT/zz-failed-ui.xml"
  adb logcat -d -s AndroidRuntime:E > "$OUT/zz-crash-log.txt" 2>/dev/null
  exit 1
}

# centre of the first node whose text / content-desc contains $1 (or class equals $1 after "class:")
find_node() {
  dump | python3 -c '
import re, sys, xml.etree.ElementTree as ET
needle = sys.argv[1]
root = ET.fromstring(sys.stdin.read() or "<x/>")
for n in root.iter("node"):
    a = n.attrib
    hit = (a.get("class") == needle[6:]) if needle.startswith("class:") else \
          needle.lower() in (a.get("text", "") + " " + a.get("content-desc", "")).lower()
    if hit:
        x1, y1, x2, y2 = map(int, re.findall(r"\d+", a["bounds"]))
        print((x1 + x2) // 2, (y1 + y2) // 2)
        break
' "$1"
}

wait_for() {  # wait_for <text> <seconds>
  local end=$((SECONDS + $2))
  while [ $SECONDS -lt $end ]; do
    [ -n "$(find_node "$1")" ] && return 0
    sleep 2
  done
  fail "did not see '$1' within $2 s"
}

tap() {
  local xy; xy=$(find_node "$1")
  [ -n "$xy" ] || fail "nothing to tap: '$1'"
  adb shell input tap $xy
  log "tapped '$1'"
}

hide_keyboard() { adb shell input keyevent 111 >/dev/null 2>&1; sleep 1; }

say() {  # type a chat message and send it
  tap "class:android.widget.EditText"
  adb shell input text "$(printf '%s' "$1" | sed 's/ /%s/g')"
  tap "Send"
  hide_keyboard
  log "sent '$1'"
}

log "installing $APK"
adb install -r "$APK" || fail "install"
adb shell am start -n "$PKG/.MainActivity" || fail "launch"

wait_for "Dashboard" 120
sleep 6                                     # fleet data loads from GitHub
shot 01-home

tap "Ask FleetLog AI"
wait_for "AI Fleet Log Assistant" 30
shot 02-chat-welcome

tap "driver LEA-22-2030"                    # suggestion chip
wait_for "chala rahe" 120
shot 03-driver-mode

say "brake se bohat awaaz aa rahi hai"
wait_for "ISS-" 150
sleep 2
shot 04-issue-report

say "kal subah slot"
wait_for "LHR" 150
sleep 2
shot 05-slots

say "pehla wala"
wait_for "BK-" 150
sleep 2
shot 06-booking-with-buttons

say "manager"
wait_for "Manager mode" 60
tap "Approve"                               # inline button on the booking alert
wait_for "driver ko bata diya" 150           # the tool's own confirmation, not the button label
sleep 3
shot 07-manager-approved

log "all steps passed"
