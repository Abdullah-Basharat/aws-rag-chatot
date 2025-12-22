"""
Plain Python load testing script for the AWS RAG Chatbot backend.

It can be run from a local Windows machine to simulate many concurrent users
logging in and sending chat messages to the FastAPI backend.

Latency measurements have been removed per user request; the script now
focuses only on success/failure counts.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import List

import requests
from requests.auth import HTTPBasicAuth


@dataclass
class RequestResult:
    ok: bool
    status_code: int
    error: str | None = None


def ensure_test_users(
    base_url: str,
    admin_username: str,
    admin_password: str,
    user_prefix: str,
    users: int,
    password: str,
) -> None:
    """
    Ensure the specified test users exist by calling the admin /admin/users endpoint.
    """
    auth = HTTPBasicAuth(admin_username, admin_password)
    for i in range(1, users + 1):
        username = f"{user_prefix}{i:03d}"
        payload = {"username": username, "password": password}
        resp = requests.post(f"{base_url}/admin/users", json=payload, auth=auth)
        # 200 -> created, 400 -> already exists
        if resp.status_code not in (200, 400):
            print(f"Failed to ensure user {username}: {resp.status_code} {resp.text}")


def user_scenario(
    base_url: str,
    username: str,
    password: str,
    messages: int,
) -> List[RequestResult]:
    auth = HTTPBasicAuth(username, password)
    results: List[RequestResult] = []

    # Login check
    resp = requests.get(f"{base_url}/user/auth/check", auth=auth)
    results.append(
        RequestResult(
            ok=resp.status_code == 200,
            status_code=resp.status_code,
            error=None if resp.status_code == 200 else resp.text,
        )
    )
    if resp.status_code != 200:
        return results

    # Chat messages
    for i in range(messages):
        payload = {"user_id": username, "message": f"Test message {i+1} from {username}"}
        resp = requests.post(f"{base_url}/user/chat", json=payload, auth=auth)
        results.append(
            RequestResult(
                ok=resp.status_code == 200,
                status_code=resp.status_code,
                error=None if resp.status_code == 200 else resp.text,
            )
        )
    return results


def run_load_test(
    base_url: str,
    num_users: int,
    messages_per_user: int,
    user_prefix: str,
    user_password: str,
) -> List[RequestResult]:
    usernames = [f"{user_prefix}{i:03d}" for i in range(1, num_users + 1)]
    all_results: List[RequestResult] = []
    with ThreadPoolExecutor(max_workers=num_users) as executor:
        futures = [
            executor.submit(
                user_scenario,
                base_url,
                username,
                user_password,
                messages_per_user,
            )
            for username in usernames
        ]
        for fut in as_completed(futures):
            all_results.extend(fut.result())
    return all_results


def summarize_results(results: List[RequestResult]) -> None:
    if not results:
        print("No requests were executed.")
        return

    successes = [r for r in results if r.ok]
    failures = [r for r in results if not r.ok]

    print("\n=== Load Test Summary ===")
    print(f"Total requests: {len(results)}")
    print(f"Successful: {len(successes)}")
    print(f"Failed: {len(failures)}")
    if failures:
        print("\nSample failures (up to 5):")
        for r in failures[:5]:
            print(f"  status={r.status_code} error={r.error!r}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Load test the RAG chatbot backend.")
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="Base URL of the FastAPI backend.",
    )
    parser.add_argument(
        "--num-users",
        type=int,
        default=20,
        help="Number of concurrent users to simulate.",
    )
    parser.add_argument(
        "--messages-per-user",
        type=int,
        default=3,
        help="Number of chat messages per simulated user.",
    )
    parser.add_argument(
        "--user-prefix",
        default="loadtest_user_",
        help="Prefix for test usernames.",
    )
    parser.add_argument(
        "--user-password",
        default="test123",
        help="Password to use for all test users.",
    )
    parser.add_argument(
        "--admin-username",
        help="Admin username for creating test users via /admin/users.",
    )
    parser.add_argument(
        "--admin-password",
        help="Admin password for creating test users via /admin/users.",
    )
    parser.add_argument(
        "--ensure-users",
        action="store_true",
        help="If set, create test users via admin API before running the test.",
    )
    args = parser.parse_args()

    if args.ensure_users:
        if not args.admin_username or not args.admin_password:
            raise SystemExit(
                "--ensure-users requires --admin-username and --admin-password"
            )
        print(
            f"Ensuring {args.num_users} test users exist via admin API at {args.base_url}..."
        )
        ensure_test_users(
            args.base_url,
            args.admin_username,
            args.admin_password,
            args.user_prefix,
            args.num_users,
            args.user_password,
        )

    print(
        f"Running load test: {args.num_users} users, "
        f"{args.messages_per_user} messages each, base URL={args.base_url}"
    )
    results = run_load_test(
        args.base_url,
        args.num_users,
        args.messages_per_user,
        args.user_prefix,
        args.user_password,
    )
    print("Completed load test.")
    summarize_results(results)


if __name__ == "__main__":
    main()


