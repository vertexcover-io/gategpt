from typing import Any
from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

openapi_schema_router = APIRouter()


def get_openapi_schema(
    openapi_schema: dict[str, Any], tags: set[str]
) -> dict[str, Any]:
    filtered_paths = {}

    for path, path_item in openapi_schema["paths"].items():
        for method, operation in path_item.items():
            if "tags" in operation and set(operation["tags"]) & tags:
                if path not in filtered_paths:
                    filtered_paths[path] = {}
                filtered_paths[path][method] = operation

    openapi_schema["paths"] = filtered_paths
    return openapi_schema


@openapi_schema_router.get(
    "/",
    response_class=JSONResponse,
    include_in_schema=False,
    name="openapi_schema_by_tags",
)
def openapi_schema_by_tags(
    request: Request,
    tags: list[str] = Query([]),
):
    openapi_schema = request.app.openapi()
    return get_openapi_schema(openapi_schema, set(tags))
