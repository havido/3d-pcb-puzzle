"""Minimal S-expression reader for KiCad files.

Every node becomes a Python list whose first element is its keyword, e.g.
`(at 1 2 90)` -> `["at", "1", "2", "90"]`. Atoms stay strings; callers convert
numbers where they need them.
"""
import re

_TOKEN = re.compile(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()"]+')
_ESCAPE = re.compile(r"\\(.)")
_ESCAPES = {"n": "\n", "t": "\t"}


class SexpError(ValueError):
    pass


def parse(text: str) -> list:
    stack: list[list] = [[]]
    for m in _TOKEN.finditer(text):
        tok = m.group(0)
        if tok == "(":
            stack.append([])
        elif tok == ")":
            if len(stack) == 1:
                raise SexpError(f"unexpected ')' at offset {m.start()}")
            node = stack.pop()
            stack[-1].append(node)
        elif tok[0] == '"':
            stack[-1].append(_ESCAPE.sub(lambda e: _ESCAPES.get(e.group(1), e.group(1)), tok[1:-1]))
        else:
            stack[-1].append(tok)
    if len(stack) != 1:
        raise SexpError(f"{len(stack) - 1} unclosed '('")
    if len(stack[0]) != 1:
        raise SexpError(f"expected one top-level expression, found {len(stack[0])}")
    return stack[0][0]


def find(node: list, key: str) -> list[list]:
    """All direct children of `node` whose keyword is `key`."""
    return [c for c in node if isinstance(c, list) and c and c[0] == key]


def first(node: list, key: str) -> list | None:
    """First direct child with keyword `key`, or None."""
    for c in node:
        if isinstance(c, list) and c and c[0] == key:
            return c
    return None


def value(node: list, key: str, default=None):
    """The first atom of child `key`, e.g. value((width 0.2), "width") -> "0.2"."""
    c = first(node, key)
    return c[1] if c is not None and len(c) > 1 else default


def xy(node: list | None) -> tuple[float, float] | None:
    """(start 1 2) -> (1.0, 2.0)."""
    return (float(node[1]), float(node[2])) if node is not None else None
