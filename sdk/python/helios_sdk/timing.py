from datetime import datetime, timezone


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def elapsed_ms(started_at: datetime, ended_at: datetime) -> int:
    delta = ended_at - started_at
    return max(0, int(delta.total_seconds() * 1000))
