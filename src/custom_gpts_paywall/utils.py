import datetime as datetime_module
from datetime import datetime
from typing import Any

from fastapi import Request


def utcnow() -> datetime:
    return datetime.now(datetime_module.UTC)


def url_for(request: Request, name: str, scheme=None, **path_params: Any) -> str:
    url = request.url_for(name, **path_params)
    url.replace(scheme=scheme or request.url.scheme)
    return str(url)
