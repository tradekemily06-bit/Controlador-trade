from __future__ import annotations

import re

REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def validate_request_id(request_id: str) -> str:
    if not isinstance(request_id, str) or not REQUEST_ID_PATTERN.fullmatch(request_id):
        raise ValueError("request_id inválido.")
    return request_id
