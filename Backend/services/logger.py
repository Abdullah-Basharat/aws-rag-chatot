import os
from datetime import datetime

from . import s3_storage


LOG_PREFIX = os.getenv("LOG_S3_PREFIX", "logs")


def log_event(user: str, event_type: str, details: str) -> None:
    """
    Log a single application event to S3.

    Each event is stored as a small text object under the configured
    prefix, keeping application nodes stateless and avoiding local files.
    """
    timestamp = datetime.utcnow().isoformat()
    line = f"[{timestamp}] user={user} event={event_type} details={details}\n"

    # Example key: logs/2025-01-01/2025-01-01T12-00-00.000000Z_user_login.log
    date_prefix = timestamp.split("T", 1)[0]
    safe_ts = timestamp.replace(":", "-")
    key = f"{LOG_PREFIX}/{date_prefix}/{safe_ts}_{event_type}.log"

    try:
        s3_storage.put_text_object(key, line)
    except Exception:
        # Logging must never break the main application flow.
        pass

