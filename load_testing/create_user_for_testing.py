"""
Create 200 users via /admin/users endpoint
------------------------------------------
Requires admin credentials.
"""

import requests
from requests.auth import HTTPBasicAuth

# ================= CONFIG =================
BASE_URL = "http://rag-chatbot-alb-v1-2019164371.us-east-1.elb.amazonaws.com:8000"
USER_PREFIX = "sandy"
PASSWORD = "12345678"
TOTAL_USERS = 200
REQUEST_TIMEOUT = 30

# Admin credentials (must be an admin user)
ADMIN_USERNAME="admin"
ADMIN_PASSWORD="1231234"

# ================= MAIN =================
def create_user(username: str, password: str) -> bool:
    try:
        resp = requests.post(
            f"{BASE_URL}/admin/users",
            json={"username": username, "password": password},
            auth=HTTPBasicAuth(ADMIN_USERNAME, ADMIN_PASSWORD),
            timeout=REQUEST_TIMEOUT
        )
        if resp.status_code == 200:
            print(f"[✅] User created: {username}")
            return True
        elif resp.status_code == 400:
            print(f"[⚠️] User already exists: {username}")
            return False
        else:
            print(f"[❌] Failed to create {username}: {resp.status_code} {resp.text}")
            return False
    except Exception as e:
        print(f"[❌] Exception for {username}: {e}")
        return False


if __name__ == "__main__":
    for i in range(1, TOTAL_USERS + 1):
        username = f"{USER_PREFIX}{i:03d}"
        create_user(username, PASSWORD)
