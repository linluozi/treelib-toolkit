# Copyright (C) 2026 treelib-toolkit contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Depth-safe JSON encoding and decoding helpers.

Why this module exists
----------------------
The standard library ``json`` module is recursive: both ``json.dumps`` and
``json.loads`` raise ``RecursionError`` once document nesting exceeds the
interpreter recursion limit (1000 by default). A tree serialised from a
1,200-deep chain therefore could not be written out, and even a JSON document
that had been produced elsewhere could not be read back.

The helpers here emit exactly the same text as ``json.dumps(obj)`` with the
default separators, and accept the same subset of JSON that ``json.loads``
accepts, but they drive the traversal with an explicit stack. Nesting depth is
therefore bounded by available memory instead of ``sys.getrecursionlimit()``.
"""

import json
import re
from json.decoder import scanstring

__all__ = ["dumps", "loads", "JSONDecodeError"]

JSONDecodeError = json.JSONDecodeError

_WS = " \t\n\r"
_NUMBER_RE = re.compile(r"-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][-+]?\d+)?")
_TRUE = "true"
_FALSE = "false"
_NULL = "null"


def _skip_ws(text, pos):
    """Advance ``pos`` past JSON whitespace."""
    length = len(text)
    while pos < length and text[pos] in _WS:
        pos += 1
    return pos


def _fail(message, text, pos):
    raise JSONDecodeError(message, text, pos)


def dumps(obj):
    """Serialise ``obj`` to JSON without recursing.

    The produced text is byte-identical to ``json.dumps(obj)`` for the same
    input, including the default ``", "`` / ``": "`` separators.
    """
    out = []
    # Each stack entry is either ("raw", text) or ("value", python object).
    stack = [("value", obj)]
    while stack:
        kind, payload = stack.pop()
        if kind == "raw":
            out.append(payload)
            continue

        if isinstance(payload, dict):
            if not payload:
                out.append("{}")
                continue
            out.append("{")
            stack.append(("raw", "}"))
            items = list(payload.items())
            last = len(items) - 1
            for index in range(last, -1, -1):
                key, value = items[index]
                if index != last:
                    stack.append(("raw", ", "))
                stack.append(("value", value))
                stack.append(("raw", json.dumps(key) + ": "))
        elif isinstance(payload, (list, tuple)):
            if not payload:
                out.append("[]")
                continue
            out.append("[")
            stack.append(("raw", "]"))
            last = len(payload) - 1
            for index in range(last, -1, -1):
                if index != last:
                    stack.append(("raw", ", "))
                stack.append(("value", payload[index]))
        else:
            out.append(json.dumps(payload))
    return "".join(out)


def _deliver(stack, value):
    """Attach ``value`` to the innermost open container.

    Returns ``(result, next_state)``. ``result`` is only set when the outermost
    value has been completed.
    """
    if not stack:
        return value, "after"
    frame = stack[-1]
    if frame[0] == "obj":
        frame[1][frame[2]] = value
        frame[2] = None
    else:
        frame[1].append(value)
    return None, "after"


def loads(text):
    """Parse a JSON document without recursing.

    Accepts ``str``, ``bytes`` or ``bytearray``. Only the standard JSON grammar
    is supported; the optional ``parse_*`` hooks of :func:`json.loads` are not.
    """
    if isinstance(text, (bytes, bytearray)):
        text = bytes(text).decode("utf-8")
    if not isinstance(text, str):
        raise TypeError("the JSON object must be str, bytes or bytearray, not %s" % type(text).__name__)

    pos = 0
    length = len(text)
    stack = []
    result = None
    state = "value"

    while True:
        if state == "value":
            pos = _skip_ws(text, pos)
            if pos >= length:
                _fail("Expecting value", text, pos)
            char = text[pos]
            if char == "{":
                frame = ["obj", {}, None]
                stack.append(frame)
                pos += 1
                state = "first_key"
            elif char == "[":
                frame = ["arr", [], None]
                stack.append(frame)
                pos += 1
                state = "first_value"
            elif char == '"':
                value, pos = scanstring(text, pos + 1, True)
                result, state = _deliver(stack, value)
            elif char == "t":
                if text[pos : pos + 4] != _TRUE:
                    _fail("Expecting value", text, pos)
                pos += 4
                result, state = _deliver(stack, True)
            elif char == "f":
                if text[pos : pos + 5] != _FALSE:
                    _fail("Expecting value", text, pos)
                pos += 5
                result, state = _deliver(stack, False)
            elif char == "n":
                if text[pos : pos + 4] != _NULL:
                    _fail("Expecting value", text, pos)
                pos += 4
                result, state = _deliver(stack, None)
            else:
                match = _NUMBER_RE.match(text, pos)
                if not match:
                    _fail("Expecting value", text, pos)
                literal = match.group(0)
                pos = match.end()
                if "." in literal or "e" in literal or "E" in literal:
                    value = float(literal)
                else:
                    value = int(literal)
                result, state = _deliver(stack, value)

        elif state == "first_key":
            pos = _skip_ws(text, pos)
            if pos < length and text[pos] == "}":
                pos += 1
                frame = stack.pop()
                result, state = _deliver(stack, frame[1])
            else:
                state = "key"

        elif state == "key":
            pos = _skip_ws(text, pos)
            if pos >= length or text[pos] != '"':
                _fail("Expecting property name enclosed in double quotes", text, pos)
            key, pos = scanstring(text, pos + 1, True)
            pos = _skip_ws(text, pos)
            if pos >= length or text[pos] != ":":
                _fail("Expecting ':' delimiter", text, pos)
            pos += 1
            stack[-1][2] = key
            state = "value"

        elif state == "first_value":
            pos = _skip_ws(text, pos)
            if pos < length and text[pos] == "]":
                pos += 1
                frame = stack.pop()
                result, state = _deliver(stack, frame[1])
            else:
                state = "value"

        elif state == "after":
            pos = _skip_ws(text, pos)
            if not stack:
                if pos != length:
                    _fail("Extra data", text, pos)
                return result
            frame = stack[-1]
            if pos >= length:
                _fail("Expecting ',' delimiter", text, pos)
            char = text[pos]
            if char == ",":
                pos += 1
                state = "key" if frame[0] == "obj" else "value"
            elif char == "}" and frame[0] == "obj":
                pos += 1
                stack.pop()
                result, state = _deliver(stack, frame[1])
            elif char == "]" and frame[0] == "arr":
                pos += 1
                stack.pop()
                result, state = _deliver(stack, frame[1])
            else:
                _fail("Expecting ',' delimiter", text, pos)
        else:  # pragma: no cover - defensive
            raise RuntimeError("unexpected parser state: %s" % state)
