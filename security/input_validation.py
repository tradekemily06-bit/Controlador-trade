from __future__ import annotations

import json
import math
from typing import Any


MAX_JSON_DEPTH = 12
MAX_OBJECT_KEYS = 64
MAX_LIST_ITEMS = 1000
MAX_STRING_LENGTH = 4096


class InputValidationError(ValueError):
    pass


def _reject_constant(value: str) -> None:
    raise InputValidationError(f"invalid JSON number: {value}")


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InputValidationError("duplicate JSON object key")
        result[key] = value
    return result


def validate_json_value(value: Any, depth: int = 0) -> Any:
    if depth > MAX_JSON_DEPTH:
        raise InputValidationError("JSON nesting too deep")
    if isinstance(value, str):
        if len(value) > MAX_STRING_LENGTH:
            raise InputValidationError("string exceeds maximum length")
        return value
    if isinstance(value, dict):
        if len(value) > MAX_OBJECT_KEYS:
            raise InputValidationError("too many object fields")
        for key, item in value.items():
            if not isinstance(key, str) or len(key) > MAX_STRING_LENGTH:
                raise InputValidationError("invalid object key")
            validate_json_value(item, depth + 1)
        return value
    if isinstance(value, list):
        if len(value) > MAX_LIST_ITEMS:
            raise InputValidationError("too many list items")
        for item in value:
            validate_json_value(item, depth + 1)
        return value
    if isinstance(value, float) and not math.isfinite(value):
        raise InputValidationError("non-finite number is not allowed")
    if value is None or isinstance(value, (bool, int, float)):
        return value
    raise InputValidationError("unsupported JSON value")
