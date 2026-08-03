"""
Test/lrcmux/run_test_and_log.py

Final integration test for lrcmux:
  - Starts the Lyrica dev server
  - Fetches LINE-LEVEL synced lyrics (timestamps=true, word=false)
  - Fetches WORD-LEVEL synced lyrics (timestamps=true, word=true)
  - Saves both responses to JSON files
  - Prints a summary + server logs
"""

import subprocess
import time
import httpx
import json
import sys
import os

test_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(test_dir))

line_file  = os.path.join(test_dir, "result_line_level.json")
word_file  = os.path.join(test_dir, "result_word_level.json")
server_log = os.path.join(test_dir, "server.log")

try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

BASE = "http://localhost:9999"
ARTIST = "Coldplay"
SONG   = "Yellow"


def _print_sep(title=""):
    print(f"\n{'='*55} {title} {'='*55}\n")


def _summarise(label: str, data: dict, out_file: str):
    d = data.get("data", {})
    timed = d.get("timed_lyrics", [])
    has_words = any("words" in ln for ln in timed)
    print(f"[{label}]")
    print(f"  status        : {data.get('status')}")
    print(f"  source        : {d.get('source')}")
    print(f"  hasTimestamps : {d.get('hasTimestamps')}")
    print(f"  sync_level    : {d.get('sync_level', 'N/A')}")
    print(f"  timed lines   : {len(timed)}")
    print(f"  word arrays   : {has_words}")
    if timed:
        sample = next((ln for ln in timed if "words" in ln), timed[0])
        print(f"  sample line   : {json.dumps(sample, ensure_ascii=False)[:200]}")
    print(f"  saved to      : {out_file}")


def run_test():
    log_f = open(server_log, "w", encoding="utf-8")
    print("Starting Flask server on port 9999 …")
    proc = subprocess.Popen(
        [sys.executable, "run.py"],
        stdout=log_f, stderr=subprocess.STDOUT,
        cwd=project_root,
        env={**os.environ, "FLASK_DEBUG": "false", "PORT": "9999"},
    )
    time.sleep(4.0)

    overall_ok = True

    with httpx.Client(timeout=30.0) as client:
        # ── Test 1: Line-level sync ──────────────────────────────────────────
        _print_sep("TEST 1 — LINE-LEVEL SYNC")
        params1 = {
            "artist": ARTIST, "song": SONG,
            "sequence": "7",
            "timestamps": "true",
            "word": "false",
        }
        try:
            r1 = client.get(f"{BASE}/lyrics/", params=params1)
            print(f"HTTP {r1.status_code}")
            data1 = r1.json()
            with open(line_file, "w", encoding="utf-8") as f:
                json.dump(data1, f, indent=2, ensure_ascii=False)
            _summarise("line-level", data1, line_file)
            if data1.get("status") != "success":
                print("  ⚠ Non-success status")
                overall_ok = False
        except Exception as e:
            print(f"  ✗ Error: {e}")
            overall_ok = False

        time.sleep(1.0)

        # ── Test 2: Word-level sync ──────────────────────────────────────────
        _print_sep("TEST 2 — WORD-LEVEL SYNC")
        params2 = {
            "artist": ARTIST, "song": SONG,
            "sequence": "7",
            "timestamps": "true",
            "word": "true",
        }
        try:
            r2 = client.get(f"{BASE}/lyrics/", params=params2)
            print(f"HTTP {r2.status_code}")
            data2 = r2.json()
            with open(word_file, "w", encoding="utf-8") as f:
                json.dump(data2, f, indent=2, ensure_ascii=False)
            _summarise("word-level", data2, word_file)
            if data2.get("status") != "success":
                print("  ⚠ Non-success status")
                overall_ok = False
        except Exception as e:
            print(f"  ✗ Error: {e}")
            overall_ok = False

    # ── Shutdown ─────────────────────────────────────────────────────────────
    print("\nStopping server …")
    proc.terminate()
    proc.wait()
    log_f.close()

    _print_sep("SERVER LOGS")
    with open(server_log, "r", encoding="utf-8", errors="replace") as f:
        print(f.read())

    _print_sep("RESULT")
    if overall_ok:
        print("✅ All tests passed")
    else:
        print("❌ One or more tests failed")
        sys.exit(1)


if __name__ == "__main__":
    run_test()
