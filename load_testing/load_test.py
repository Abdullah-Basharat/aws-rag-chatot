"""
ECS Auto-Scaling Load Test for RAG App
--------------------------------------
Simulates users ramping from 0 → TOTAL_USERS over a ramp duration,
holds high load for sustained period, then ramps down.
Prints all request results to console.
"""

import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import List
import requests
from requests.auth import HTTPBasicAuth

# ================= CONFIG =================
BASE_URL = "http://rag-chatbot-alb-v1-2019164371.us-east-1.elb.amazonaws.com:8000"
USER_PREFIX = "sandy"
PASSWORD = "12345678"

TOTAL_USERS = 120
RAMP_UP_DURATION = 300        # seconds, 0 -> TOTAL_USERS
SUSTAIN_DURATION = 180        # seconds at full load
RAMP_DOWN_DURATION = 180      # seconds, full load -> 0
REQUEST_TIMEOUT = 30          # seconds

# Threading lock for safe result recording
lock = threading.Lock()

@dataclass
class Result:
    user: str
    timestamp: float
    ok: bool
    status: int
    error: str | None

results: List[Result] = []

# ================= FUNCTIONS =================

def send_chat(user: str) -> None:
    """Send a single chat message for a user"""
    ts = time.time()
    try:
        resp = requests.post(
            f"{BASE_URL}/user/chat",
            json={"user_id": user, "message": "Load test message"},
            auth=HTTPBasicAuth(user, PASSWORD),
            timeout=REQUEST_TIMEOUT,
        )
        ok = resp.status_code == 200
        err = None if ok else resp.text
    except Exception as e:
        ok = False
        err = str(e)
        resp = type("Resp", (), {"status_code": 0})()  # dummy

    with lock:
        results.append(Result(user=user, timestamp=ts, ok=ok, status=resp.status_code, error=err))


def run_phase(users: List[str], concurrency: int, duration_seconds: int, phase_name: str) -> None:
    print(f"\n▶ Phase: {phase_name} | concurrency={concurrency} | duration={duration_seconds}s")
    end_time = time.time() + duration_seconds

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        while time.time() < end_time:
            futures = [executor.submit(send_chat, user) for user in users[:concurrency]]
            for _ in as_completed(futures):
                pass
            time.sleep(1)  # 1-second pacing between batches


def ramp(users: List[str], start: int, end: int, duration_seconds: int, phase_name: str) -> None:
    """Gradually ramp user concurrency from start -> end over duration"""
    print(f"\n▶ Ramp phase: {phase_name} | {start} -> {end} users over {duration_seconds}s")
    steps = end - start
    if steps <= 0:
        return

    interval = duration_seconds / steps
    current = start
    while current < end:
        run_phase(users, concurrency=current, duration_seconds=int(interval), phase_name=f"{phase_name} step {current}")
        current += 1


def summarize() -> None:
    total = len(results)
    success = sum(1 for r in results if r.ok)
    failed = total - success

    print("\n=== LOAD TEST SUMMARY ===")
    print(f"Total requests sent : {TOTAL_USERS}")
    print(f"Responses received  : {total}")
    print(f"Successful          : {success}")
    print(f"Failed              : {failed}")

    if failed:
        print("\nSample failures (up to 5):")
        for r in results[:5]:
            if not r.ok:
                print(f"User={r.user} status={r.status} error={r.error}")


# ================= MAIN =================
if __name__ == "__main__":
    users = [f"{USER_PREFIX}{i:03d}" for i in range(1, TOTAL_USERS + 1)]

    start_time = time.time()

    # 1️⃣ Ramp up from 0 -> TOTAL_USERS
    ramp(users, start=1, end=TOTAL_USERS, duration_seconds=RAMP_UP_DURATION, phase_name="RAMP UP")

    # 2️⃣ Sustained high load
    run_phase(users, concurrency=TOTAL_USERS, duration_seconds=SUSTAIN_DURATION, phase_name="SUSTAIN HIGH LOAD")

    # 3️⃣ Ramp down from TOTAL_USERS -> 0
    ramp(users, start=TOTAL_USERS, end=0, duration_seconds=RAMP_DOWN_DURATION, phase_name="RAMP DOWN")

    # 4️⃣ Summarize
    summarize()

    end_time = time.time()
    print(f"\nTest completed in {end_time - start_time:.2f} seconds")
