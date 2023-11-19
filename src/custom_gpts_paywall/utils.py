import datetime as datetime_module
from datetime import datetime


def utcnow() -> datetime:
    return datetime.now(datetime_module.UTC)
