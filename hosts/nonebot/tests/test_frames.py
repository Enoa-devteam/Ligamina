"""Host frames must be well-formed UTF-8 JSON (see crates/ligamina-core/tests/host_session.rs).

A plugin can build text from surrogate escapes (for example the pair U+D83D U+DCF0 for an emoji).
Encoding that text as UTF-8 raised and lost the frame; the Core also closes the whole session on a
lone-surrogate escape.
"""

import json
from pathlib import Path

from ligamina_nonebot.frames import encode_frame


def test_surrogate_pairs_become_characters_and_lone_surrogates_become_replacement() -> None:
    frame = encode_frame({"result": {"text": "\ud83d\udcf0 news \ud800 end", "keys": {"k\udcff": ["\udc00"]}}})
    assert frame.endswith(b"\n")
    text = frame.decode("utf-8", errors="strict")
    assert "\\ud" not in text.lower()
    packet = json.loads(text)
    assert packet["result"]["text"] == "\U0001f4f0 news \ufffd end"
    assert packet["result"]["keys"] == {"k\ufffd": ["\ufffd"]}


def test_ordinary_frames_are_unchanged() -> None:
    packet = {"jsonrpc": "2.0", "id": 1, "result": {"text": "普通文本", "n": 3, "ok": True, "none": None}}
    assert encode_frame(packet) == (json.dumps(packet, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def test_worker_sends_every_frame_through_encode_frame() -> None:
    source = (Path(__file__).resolve().parents[1] / "ligamina_nonebot/worker.py").read_text(encoding="utf-8")
    assert "encode_frame(packet)" in source
    assert '.encode("utf-8")' not in source
