import functools
import json
import threading
import time
from datetime import datetime
from typing import Any, cast
from zoneinfo import ZoneInfo

threadLocal = threading.local()


class TIM:
    def __init__(self, name):
        self.name = name

    def __enter__(self):
        self.start = time.time()
        self.level = getattr(threadLocal, "level", "")
        threadLocal.level = self.level + "  "

    def __exit__(self, type, value, traceback):
        stop = time.time()
        threadLocal.level = self.level
        print("%s%s: %s ms" % (self.level, self.name, (stop - self.start) * 1000))


def timeit(f):
    if callable(f):

        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            with TIM(f.__name__):
                return f(*args, **kwargs)

        return wrapper

    # otherwise it is a context manager
    return TIM(f)


def oai_context(entry: StreamEntry) -> dict[str, str]:
    """Get the OAI context from the entry."""
    return cast(dict[str, str], entry.context["oai"]) if "oai" in entry.context else {}


def parse_iso_to_utc(datetime_str: str) -> datetime:
    """
    Parse an ISO datetime string and return a naive UTC datetime object.

    - If the input has no timezone, it's treated as UTC.
    - If the input has a timezone, it's converted to UTC.
    - The returned datetime is naive (no timezone info).

    :param datetime_str: ISO format datetime string

    :return datetime: naive datetime object in UTC
    """
    dt = datetime.fromisoformat(datetime_str)

    if dt.tzinfo is None:
        return dt

    dt = dt.astimezone(ZoneInfo("UTC"))
    return dt.replace(tzinfo=None)


def get_oai_datestamp(dt: datetime) -> str:
    """
    Get the datestamp from a datetime object.

    :param datetime: datetime object

    :return: ISO format string
    """
    # convert to UTC, and make it naive
    if dt.tzinfo is not None:
        dt = dt.astimezone(ZoneInfo("UTC"))
        dt = dt.replace(tzinfo=None)

    # oai needs 'Z' at the end, so add it after seconds
    formatted = dt.isoformat()
    formatted += "Z"
    return formatted


def make_safe_json(data: Any):
    if data is None:
        return None
    return json.loads(json.dumps(data, default=lambda x: str(x)))
