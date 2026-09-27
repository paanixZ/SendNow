"""Emit KeyValues3 text in the layout used by Facepunch's shipped .vmdl files.

The header and formatting are copied from real files in Facepunch/sbox-public
(templates/sbox/reference, commit recorded in templates/sbox/reference/SOURCE.md).
"""

from __future__ import annotations

MODELDOC_HEADER = (
    "<!-- kv3 encoding:text:version{e21c7f3c-8a33-41c5-9977-a76d3a32aa0d} "
    "format:modeldoc29:version{3cec427c-1b0e-4d48-a90a-0436f33a6041} -->"
)


class Raw(str):
    """Pre-formatted value (not quoted)."""


def _fmt_scalar(v) -> str:
    if isinstance(v, Raw):
        return str(v)
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        s = f"{v:.6f}".rstrip("0")
        return s + "0" if s.endswith(".") else s
    if isinstance(v, str):
        return '"' + v.replace("\\", "/").replace('"', "'") + '"'
    raise TypeError(type(v))


def _emit(v, indent: int) -> list[str]:
    tab = "\t" * indent
    if isinstance(v, dict):
        lines = [tab + "{"]
        for k, val in v.items():
            if isinstance(val, (dict, list)) and not _flat_list(val):
                lines.append(f"{tab}\t{k} = ")
                lines += _emit(val, indent + 1)
            else:
                lines.append(f"{tab}\t{k} = {_inline(val)}")
        lines.append(tab + "}")
        return lines
    if isinstance(v, list):
        lines = [tab + "["]
        for item in v:
            if isinstance(item, (dict, list)):
                sub = _emit(item, indent + 1)
                sub[-1] += ","
                lines += sub
            else:
                lines.append(f"{tab}\t{_fmt_scalar(item)},")
        lines.append(tab + "]")
        return lines
    return [tab + _fmt_scalar(v)]


def _flat_list(v) -> bool:
    return isinstance(v, list) and (
        not v or all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in v)
    )


def _inline(v) -> str:
    if isinstance(v, list):
        return "[  ]" if not v else "[ " + ", ".join(_fmt_scalar(float(x)) for x in v) + " ]"
    return _fmt_scalar(v)


def dumps_modeldoc(root: dict) -> str:
    return MODELDOC_HEADER + "\n" + "\n".join(_emit({"rootNode": root}, 0)) + "\n"


def parse_kv3(text: str):
    """Small KV3 text parser, used to validate our own output structurally in tests."""
    i = 0
    n = len(text)
    if text.startswith("<!--"):
        i = text.index("-->") + 3

    def ws():
        nonlocal i
        while i < n:
            if text[i].isspace():
                i += 1
            elif text.startswith("//", i):
                i = text.find("\n", i)
                i = n if i < 0 else i
            else:
                break

    def string():
        nonlocal i
        if text.startswith('"""', i):
            j = text.index('"""', i + 3)
            s = text[i + 3 : j]
            i = j + 3
            return s
        out = []
        j = i + 1
        while text[j] != '"':
            if text[j] == "\\":
                j += 1
                out.append({"n": "\n", "t": "\t"}.get(text[j], text[j]))
            else:
                out.append(text[j])
            j += 1
        i = j + 1
        return "".join(out)

    def value():
        nonlocal i
        ws()
        c = text[i]
        if c == "{":
            i += 1
            obj = {}
            while True:
                ws()
                if text[i] == "}":
                    i += 1
                    return obj
                if text[i] == '"':
                    key = string()
                else:
                    j = i
                    while not text[j].isspace() and text[j] != "=":
                        j += 1
                    key = text[i:j]
                    i = j
                ws()
                if text[i] != "=":
                    raise ValueError(f"expected '=' after {key!r} at {i}")
                i += 1
                obj[key] = value()
        if c == "[":
            i += 1
            arr = []
            while True:
                ws()
                if text[i] == "]":
                    i += 1
                    return arr
                arr.append(value())
                ws()
                if text[i] == ",":
                    i += 1
        if c == '"':
            return string()
        j = i
        while j < n and not text[j].isspace() and text[j] not in ",]}":
            j += 1
        tok = text[i:j]
        i = j
        if tok in ("true", "false"):
            return tok == "true"
        try:
            return float(tok) if "." in tok else int(tok)
        except ValueError:
            return tok

    result = value()
    ws()
    if i != n:
        raise ValueError(f"trailing data at {i}")
    return result
