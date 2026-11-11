from datetime import datetime, timezone


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def money(value: float) -> float:
    return round(float(value), 2)


def copies(count: int) -> str:
    return "copy" if count == 1 else "copies"
