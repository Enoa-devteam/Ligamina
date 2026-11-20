import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { encodeFrame } from "../dist/frames.js";

// The Core parses Host frames strictly: a lone surrogate escape ("\ud800") closes the whole Host
// session (crates/ligamina-core/tests/host_session.rs), so frames must carry well-formed Unicode.
test("lone surrogates become U+FFFD and paired ones stay real characters", () => {
  const frame = encodeFrame({ result: { text: "\ud83d\udcf0 news \ud800 end", keys: { "k\udcff": ["\udc00"] } } });
  const text = frame.toString("utf8");
  assert.ok(text.endsWith("\n"));
  assert.ok(!/\\ud[89a-f]/i.test(text), text);
  const packet = JSON.parse(text);
  assert.equal(packet.result.text, "\u{1f4f0} news \ufffd end");
  assert.deepEqual(packet.result.keys, { "k\ufffd": ["\ufffd"] });
});

test("ordinary frames are byte-identical to JSON.stringify", () => {
  const packet = { jsonrpc: "2.0", id: 1, result: { text: "普通文本", n: 3, ok: true, none: null, list: [1, "x"] } };
  assert.deepEqual(encodeFrame(packet), Buffer.from(`${JSON.stringify(packet)}\n`, "utf8"));
});

test("the worker sends every frame through encodeFrame", () => {
  const source = readFileSync(fileURLToPath(new URL("../src/worker.ts", import.meta.url)), "utf8");
  assert.ok(source.includes("encodeFrame(packet)"));
  assert.ok(!source.includes("JSON.stringify(packet)"));
});
