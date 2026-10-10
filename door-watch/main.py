"""door-watch: Telegram alerts for the Tapo C220.

- Cat: listens to Frigate events over MQTT and sends the snapshot.
- Door: compares the door region (DOOR_ROI) of Frigate's latest frame with a
  reference picture of the closed door (edge comparison, day/night references).

Usage:
  python main.py run                         # service (default in Dockerfile)
  python main.py capture-reference [day|night]  # door CLOSED, replaces references of that mode
  python main.py add-reference [day|night]      # door CLOSED, adds one more (other lighting)
  python main.py debug                       # saves /data/debug_*.png and prints score
"""

import json
import logging
import os
import sys
import threading
import time
from collections import OrderedDict
from pathlib import Path

import cv2
import numpy as np
import paho.mqtt.client as mqtt
import requests

FRIGATE_URL = os.environ.get("FRIGATE_URL", "http://frigate:5000")
CAMERA = os.environ.get("CAMERA", "tapo_c220")
MQTT_HOST = os.environ.get("MQTT_HOST", "mosquitto")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

CAT_LABELS = {l.strip() for l in os.environ.get("CAT_LABELS", "cat").split(",") if l.strip()}
CAT_COOLDOWN_S = float(os.environ.get("CAT_COOLDOWN_S", "300"))

DOOR_ROI = os.environ.get("DOOR_ROI", "")  # x,y,w,h in detect resolution (640x360)
DOOR_INTERVAL_S = float(os.environ.get("DOOR_INTERVAL_S", "5"))
DOOR_THRESHOLD = float(os.environ.get("DOOR_THRESHOLD", "0.15"))
DOOR_THRESHOLD_NIGHT = float(os.environ.get("DOOR_THRESHOLD_NIGHT") or DOOR_THRESHOLD)
MAX_REFERENCES = int(os.environ.get("MAX_REFERENCES", "10"))
DOOR_CONSECUTIVE = int(os.environ.get("DOOR_CONSECUTIVE", "3"))
DOOR_OPEN_ALERT_S = float(os.environ.get("DOOR_OPEN_ALERT_S", "600"))  # 0 = no reminder
NIGHT_SATURATION = float(os.environ.get("NIGHT_SATURATION", "12"))
DOOR_MODE = os.environ.get("DOOR_MODE", "auto")  # auto / day / night

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("door-watch")


# ---------- Telegram ----------

def telegram(text, photo=None):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log.warning("Telegram not configured, message: %s", text)
        return
    base = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
    try:
        if photo is not None:
            r = requests.post(f"{base}/sendPhoto", data={"chat_id": TELEGRAM_CHAT_ID, "caption": text},
                              files={"photo": ("photo.jpg", photo, "image/jpeg")}, timeout=20)
        else:
            r = requests.post(f"{base}/sendMessage", data={"chat_id": TELEGRAM_CHAT_ID, "text": text}, timeout=20)
        if not r.ok:
            log.error("Telegram error %s: %s", r.status_code, hide_token(r.text))
    except requests.RequestException as e:
        log.error("Telegram request failed: %s", hide_token(str(e)))


def hide_token(text):
    return text.replace(TELEGRAM_BOT_TOKEN, "***") if TELEGRAM_BOT_TOKEN else text


# ---------- Frigate ----------

def fetch_latest_jpg():
    r = requests.get(f"{FRIGATE_URL}/api/{CAMERA}/latest.jpg", timeout=10)
    r.raise_for_status()
    return r.content


def decode(jpg):
    frame = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError("could not decode frame")
    return frame


# ---------- Cat (MQTT events) ----------

class CatWatcher:
    def __init__(self):
        self.alerted = OrderedDict()
        self.last_alert = 0.0
        self.lock = threading.Lock()
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="door-watch")
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

    def start(self):
        self.client.connect_async(MQTT_HOST, MQTT_PORT)
        self.client.loop_start()

    def on_connect(self, client, userdata, flags, reason_code, properties):
        log.info("MQTT connected (%s), subscribing to frigate/events", reason_code)
        client.subscribe("frigate/events")

    def on_message(self, client, userdata, msg):
        try:
            event = json.loads(msg.payload)
        except ValueError:
            return
        after = event.get("after") or {}
        if after.get("camera") != CAMERA or after.get("label") not in CAT_LABELS:
            return
        if event.get("type") == "end" or not after.get("has_snapshot"):
            return
        event_id = after.get("id")
        with self.lock:
            if event_id in self.alerted:
                return
            self.alerted[event_id] = True
            while len(self.alerted) > 200:
                self.alerted.popitem(last=False)
            now = time.time()
            if now - self.last_alert < CAT_COOLDOWN_S:
                log.info("Cat event %s skipped (cooldown)", event_id)
                return
            self.last_alert = now
        threading.Thread(target=self.send, args=(event_id, after), daemon=True).start()

    def send(self, event_id, after):
        label = after.get("label")
        score = after.get("top_score") or after.get("score") or 0
        log.info("Cat detected: event %s score %.2f", event_id, score)
        try:
            r = requests.get(f"{FRIGATE_URL}/api/events/{event_id}/snapshot.jpg",
                             params={"crop": 1, "bbox": 1}, timeout=10)
            r.raise_for_status()
            photo = r.content
        except requests.RequestException as e:
            log.error("Snapshot download failed: %s", e)
            photo = None
        telegram(f"🐱 {label} detectado ({score:.0%})", photo)


# ---------- Door (ROI comparison) ----------

def parse_roi():
    try:
        x, y, w, h = (int(v) for v in DOOR_ROI.split(","))
    except ValueError:
        raise SystemExit("DOOR_ROI must be 'x,y,w,h' (detect resolution, e.g. 640x360)")
    return x, y, w, h


def crop(frame, roi):
    x, y, w, h = roi
    fh, fw = frame.shape[:2]
    x, y = max(0, x), max(0, y)
    w, h = min(w, fw - x), min(h, fh - y)
    if w <= 0 or h <= 0:
        raise SystemExit(f"DOOR_ROI {roi} is outside the frame ({fw}x{fh})")
    return frame[y:y + h, x:x + w]


def saturation(frame):
    return cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)[:, :, 1].mean()


def detect_mode(frame):
    if DOOR_MODE in ("day", "night"):
        return DOOR_MODE
    # IR night mode gives an almost grayscale image
    return "night" if saturation(frame) < NIGHT_SATURATION else "day"


def edges(region):
    gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
    gray = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    return cv2.Canny(gray, 50, 150) > 0


def door_score(region, reference):
    """0 = same edges as the closed reference, 1 = completely different."""
    if region.shape != reference.shape:
        reference = cv2.resize(reference, (region.shape[1], region.shape[0]))
    cur, ref = edges(region), edges(reference)
    kernel = np.ones((5, 5), np.uint8)
    cur_d = cv2.dilate(cur.astype(np.uint8), kernel) > 0
    ref_d = cv2.dilate(ref.astype(np.uint8), kernel) > 0
    mismatch = np.count_nonzero(cur & ~ref_d) + np.count_nonzero(ref & ~cur_d)
    # floor avoids a few noise edges dominating on smooth (low texture) doors
    total = max(np.count_nonzero(cur) + np.count_nonzero(ref), 0.05 * cur.size)
    return min(1.0, mismatch / total)


def threshold(mode):
    return DOOR_THRESHOLD_NIGHT if mode == "night" else DOOR_THRESHOLD


def reference_paths(mode):
    # reference_closed_day.png (legacy) + reference_closed_day_<n>.png
    return sorted(DATA_DIR.glob(f"reference_closed_{mode}*.png"))


def load_references(mode):
    """Closed-door references for mode, falling back to the other mode."""
    for m in (mode, "night" if mode == "day" else "day"):
        refs = [(p.name, img) for p in reference_paths(m) if (img := cv2.imread(str(p))) is not None]
        if refs:
            return refs, m
    return [], None


def best_score(region, refs):
    """Lowest score against all references (the closest lighting wins)."""
    scores = [(door_score(region, img), name) for name, img in refs]
    return min(scores)


class DoorWatcher:
    def __init__(self):
        self.roi = parse_roi()
        self.state = None  # "open" / "closed"
        self.streak = 0
        self.opened_at = 0.0
        self.last_reminder = 0.0
        self.warned_no_reference = False
        self.warned_fallback = False

    def run(self):
        log.info("Door watcher started, ROI=%s threshold day=%.2f night=%.2f",
                 self.roi, DOOR_THRESHOLD, DOOR_THRESHOLD_NIGHT)
        while True:
            try:
                self.tick()
            except (requests.RequestException, ValueError) as e:
                log.warning("Door check failed: %s", e)
            time.sleep(DOOR_INTERVAL_S)

    def tick(self):
        jpg = fetch_latest_jpg()
        frame = decode(jpg)
        mode = detect_mode(frame)
        refs, ref_mode = load_references(mode)
        if not refs:
            if not self.warned_no_reference:
                self.warned_no_reference = True
                log.warning("No reference yet, run: docker compose exec door-watch python main.py capture-reference")
            return
        self.warned_no_reference = False
        if ref_mode != mode and not self.warned_fallback:
            log.warning("No %s reference, using %s ones (expect false alarms): run capture-reference %s",
                        mode, ref_mode, mode)
        self.warned_fallback = ref_mode != mode
        score, ref_name = best_score(crop(frame, self.roi), refs)
        observed = "open" if score > threshold(mode) else "closed"
        log.debug("score=%.3f mode=%s ref=%s observed=%s", score, mode, ref_name, observed)

        if observed == self.state:
            self.streak = 0
            self.remind(jpg)
            return
        self.streak += 1
        if self.streak < DOOR_CONSECUTIVE:
            return
        previous, self.state, self.streak = self.state, observed, 0
        log.info("Door %s (score %.3f, %s, ref %s)", observed, score, mode, ref_name)
        if observed == "open":
            self.opened_at = self.last_reminder = time.time()
        if previous is None:
            return  # initial state, no alert
        if observed == "open":
            telegram(f"🚪 Puerta abierta (score {score:.2f}, {mode})", jpg)
        else:
            telegram("✅ Puerta cerrada", jpg)

    def remind(self, jpg):
        if self.state != "open" or DOOR_OPEN_ALERT_S <= 0:
            return
        now = time.time()
        if now - self.last_reminder >= DOOR_OPEN_ALERT_S:
            self.last_reminder = now
            minutes = int((now - self.opened_at) // 60)
            telegram(f"⚠️ La puerta sigue abierta ({minutes} min)", jpg)


# ---------- CLI ----------

def capture_reference(mode=None, add=False):
    frame = decode(fetch_latest_jpg())
    detected = detect_mode(frame)
    mode = mode or detected
    if mode not in ("day", "night"):
        raise SystemExit("mode must be 'day' or 'night'")
    if mode != detected:
        print(f"Warning: saving a {mode} reference but the camera looks like {detected} "
              f"(saturation={saturation(frame):.1f}, night below {NIGHT_SATURATION})")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    existing = reference_paths(mode)
    if not add:
        for p in existing:
            p.unlink()
        existing = []
    elif len(existing) >= MAX_REFERENCES:
        existing[0].unlink()  # drop the oldest
        print(f"Removed {existing[0]} (max {MAX_REFERENCES})")
    stamp, n = time.strftime("%Y%m%d-%H%M%S"), 0
    while (path := DATA_DIR / f"reference_closed_{mode}_{stamp}{f'-{n}' if n else ''}.png").exists():
        n += 1
    cv2.imwrite(str(path), crop(frame, parse_roi()))
    print(f"Saved {path} ({len(reference_paths(mode))} {mode} reference(s))")


def compare_image(region, reference):
    """reference | current | edges (red = only in current, blue = only in reference)."""
    reference = cv2.resize(reference, (region.shape[1], region.shape[0]))
    cur, ref = edges(region), edges(reference)
    diff = np.zeros_like(region)
    diff[cur & ref] = (255, 255, 255)
    diff[cur & ~ref] = (0, 0, 255)
    diff[ref & ~cur] = (255, 0, 0)
    return np.hstack([reference, region, diff])


def debug():
    roi = parse_roi()
    frame = decode(fetch_latest_jpg())
    mode = detect_mode(frame)
    x, y, w, h = roi
    marked = frame.copy()
    cv2.rectangle(marked, (x, y), (x + w, y + h), (0, 0, 255), 2)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(DATA_DIR / "debug_roi.png"), marked)
    region = crop(frame, roi)
    cv2.imwrite(str(DATA_DIR / "debug_edges.png"), edges(region).astype(np.uint8) * 255)
    print(f"Frame {frame.shape[1]}x{frame.shape[0]}, mode={mode} (DOOR_MODE={DOOR_MODE}, saturation={saturation(frame):.1f}, night below {NIGHT_SATURATION}), ROI={roi}")
    refs, ref_mode = load_references(mode)
    if not refs:
        print("No reference yet (run capture-reference with the door closed)")
        return
    if ref_mode != mode:
        print(f"Warning: no {mode} reference, comparing with {ref_mode} ones")
    for name, img in refs:
        print(f"  {name}: {door_score(region, img):.3f}")
    score, ref_name = best_score(region, refs)
    best = next(img for name, img in refs if name == ref_name)
    cv2.imwrite(str(DATA_DIR / "debug_compare.png"), compare_image(region, best))
    state = "OPEN" if score > threshold(mode) else "closed"
    print(f"score={score:.3f} (threshold {threshold(mode)}) -> {state}, best reference={ref_name}")
    print(f"Saved {DATA_DIR / 'debug_compare.png'} (reference | current | edge diff)")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"
    if cmd in ("capture-reference", "add-reference"):
        capture_reference(sys.argv[2] if len(sys.argv) > 2 else None, add=cmd == "add-reference")
    elif cmd == "debug":
        debug()
    elif cmd == "run":
        CatWatcher().start()
        if DOOR_ROI:
            DoorWatcher().run()
        else:
            log.warning("DOOR_ROI not set, only cat alerts are enabled")
            threading.Event().wait()
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
