from __future__ import annotations

import re


def parse_count(value) -> int:
    if value is None or value == "":
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)

    text = str(value).strip().replace(",", "")
    match = re.match(r"^([0-9]+(?:\.[0-9]+)?)(万|w|W|千|k|K)?$", text)
    if not match:
        digits = re.sub(r"[^0-9.]", "", text)
        return int(float(digits)) if digits else 0

    number = float(match.group(1))
    unit = match.group(2)
    if unit in {"万", "w", "W"}:
        number *= 10000
    elif unit in {"千", "k", "K"}:
        number *= 1000
    return int(number)
