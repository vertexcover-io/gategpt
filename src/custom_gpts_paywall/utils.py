import datetime as datetime_module
from datetime import datetime
from typing import Any
from urllib.parse import urlencode

from fastapi import Request


def utcnow() -> datetime:
    return datetime.now(datetime_module.UTC)


#  datetime.utcnow()


def url_for(
    request: Request,
    name: str,
    scheme=None,
    query_params: dict[str, Any] = None,
    **path_params: Any,
) -> str:
    url = request.url_for(name, **path_params)
    print(url)
    replace_kwargs = dict(scheme=scheme or request.url.scheme)
    if query_params:
        replace_kwargs["query"] = urlencode(query_params)
    return str(url.replace(**replace_kwargs))
