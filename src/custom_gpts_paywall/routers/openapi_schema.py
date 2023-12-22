from typing import Any
from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from custom_gpts_paywall.config import OpenAPISchemaTags

openapi_schema_router = APIRouter()


def find_values_with_key(nested_dict: dict, target_key: str):
    """
    Find all values associated with a specific key in a nested dictionary.
    :param nested_dict: The nested dictionary to search.
    :param target_key: The target key to search for.
    :return: A list of values associated with the target key.
    """
    found_values = []

    def recurse_through_dict(current_dict):
        for key, value in current_dict.items():
            if key == target_key:
                found_values.append(value)
            if isinstance(value, dict):
                recurse_through_dict(value)

    recurse_through_dict(nested_dict)
    return found_values


def filter_openapi_schema_by_tags(schema: dict[str, Any], tags: set[OpenAPISchemaTags]):
    """
    Filter an OpenAPI schema to include only paths, components, and security schemes related to specified tags.
    :param schema: The original OpenAPI schema.
    :param tags: A list of tags to filter by.
    :return: A filtered OpenAPI schema.
    """
    filtered_schema = {
        "openapi": schema["openapi"],
        "info": schema["info"],
        "paths": {},
        "components": {
            "schemas": {},
            "securitySchemes": {},
        },
    }

    # Helper function to parse component references
    def parse_component_ref(ref):
        if ref.startswith("#/components/"):
            component_type, component_name = ref.split("/")[-2:]
            return component_type, component_name
        return None, None

    # Collect necessary components
    required_components = {
        "schemas": set(),
        "securitySchemes": set(),
    }

    # Filter paths by tags and collect components
    for path, methods in schema["paths"].items():
        for method, details in methods.items():
            if (
                any(OpenAPISchemaTags(tag) in tags for tag in details.get("tags", []))
                or not tags
            ):
                # Add path if it matches the tag
                if path not in filtered_schema["paths"]:
                    filtered_schema["paths"][path] = {}
                filtered_schema["paths"][path][method] = details

                # Collect components in requestBody
                #
                request_body_components = find_values_with_key(
                    details.get("requestBody", {}), "$ref"
                )
                for request_body_ref in request_body_components:
                    if request_body_ref:
                        _, component_name = parse_component_ref(request_body_ref)
                        required_components["schemas"].add(component_name)

                response_body_components = find_values_with_key(
                    details.get("responses", {}), "$ref"
                )
                print(response_body_components)
                for response_ref in response_body_components:
                    if response_ref:
                        _, component_name = parse_component_ref(response_ref)
                        required_components["schemas"].add(component_name)

                # Collect securitySchemes
                for sec_req in details.get("security", []):
                    for sec_key in sec_req.keys():
                        required_components["securitySchemes"].add(sec_key)

    # Add required components to the filtered schema
    for component_type, component_names in required_components.items():
        for component_name in component_names:
            filtered_schema["components"][component_type][component_name] = schema[
                "components"
            ][component_type][component_name]

    return filtered_schema


# Usage Example
# Assuming `original_schema` is your full OpenAPI schema and `tags_list` is your list of tags
# filtered_schema = filter_openapi_schema_by_tags(original_schema, tags_list)


@openapi_schema_router.get(
    "/",
    response_class=JSONResponse,
    include_in_schema=False,
    name="openapi_schema_by_tags",
)
def openapi_schema_by_tags(
    request: Request,
    tags: list[OpenAPISchemaTags] = Query([]),
):
    openapi_schema = request.app.openapi()
    return filter_openapi_schema_by_tags(openapi_schema, set(tags))
