"""Well-formed UTF-8 NDJSON frames for the Core protocol.

Plugins may build text from surrogate escapes (for example the pair U+D83D U+DCF0 for an emoji).
Such a ``str`` cannot be encoded as UTF-8, and the Core closes the whole Host session on a frame
holding a lone-surrogate escape (crates/ligamina-core/tests/host_session.rs). Text is therefore
read as a UTF-16 consumer would: a valid pair becomes its character and a lone surrogate becomes
U+FFFD. Text that is already encodable is left unchanged byte for byte.
"""

from __future__ import annotations

import json
from typing import Any


def well_formed(value: Any) -> Any:
    if isinstance(value, str):
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            return value.encode("utf-16-le", "surrogatepass").decode("utf-16-le", "replace")
        return value
    if isinstance(value, dict):
        return {well_formed(key): well_formed(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [well_formed(item) for item in value]
    return value


def encode_frame(packet: dict[str, Any]) -> bytes:
    return (json.dumps(well_formed(packet), ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
