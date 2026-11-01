"""Read resolved LLVM DWARF4 scope ranges; keep incomparable paths ambiguous.

Only the pinned llvm-dwarfdump --debug-info text format is supported. Raw
strings remain private to the caller; publish only a validated projection.
"""
from collections import Counter
import re

DIE = re.compile(r"^0x([0-9a-f]+):( +)(DW_TAG_\w+|NULL)\s*$")
ATTRIBUTE = re.compile(r"\bDW_AT_(\w+)\s+\((.*)")
RANGE = re.compile(r"\[0x([0-9a-f]+),\s*0x([0-9a-f]+)\)")
NUMERIC = {"abstract_origin", "specification", "low_pc", "high_pc", "decl_line", "call_line", "call_column"}
STRINGS = {"name", "decl_file", "call_file"}
FUNCTIONS = {"DW_TAG_subprogram", "DW_TAG_inlined_subroutine"}


def merged_ranges(ranges):
    result = []
    for start, end in sorted(ranges):
        assert start <= end, "Reversed scope range"
        if start == end:
            continue
        if result and start <= result[-1][1]:
            result[-1] = (result[-1][0], max(end, result[-1][1]))
        else:
            result.append((start, end))
    return result


def parse_scopes(text):
    versions = re.findall(r"version = 0x([0-9a-f]+)", text)
    assert versions and all(int(v, 16) == 4 for v in versions), "Expected resolved DWARF4"
    nodes, stack, current, ranges = {}, [], None, False
    for line in text.splitlines():
        if line.startswith(".debug_ranges contents:"):
            break
        match = DIE.match(line)
        if match:
            offset, spaces, tag = match.groups()
            depth = len(spaces)
            while stack and stack[-1][0] >= depth:
                stack.pop()
            current, ranges = None, False
            if tag == "NULL":
                continue
            offset = int(offset, 16)
            assert offset not in nodes, "Duplicate scope DIE"
            current = {"offset": offset, "tag": tag, "parent": stack[-1][1] if stack else None,
                       "attributes": {}, "rangeRows": []}
            nodes[offset] = current
            stack.append((depth, offset))
            continue
        if current is None:
            continue
        match = ATTRIBUTE.search(line)
        if match:
            key, value = match.groups()
            ranges = key == "ranges"
            if ranges:
                current["hasRanges"] = True
            elif key in NUMERIC:
                if key in ("low_pc", "high_pc") and value.startswith("dead code"):
                    current["dead"] = True
                    continue
                number = re.match(r"(0x[0-9a-f]+|[0-9]+)", value)
                assert number, "Unsupported numeric scope attribute"
                raw = number.group()
                current["attributes"][key] = int(raw, 16 if raw.startswith("0x") else 10)
            elif key in STRINGS:
                quoted = re.match(r'"(.*)"\)', value)
                assert quoted, "Unsupported string scope attribute"
                current["attributes"][key] = quoted.group(1)
        if ranges:
            current["rangeRows"].extend((int(a, 16), int(b, 16)) for a, b in RANGE.findall(line))
    for node in nodes.values():
        attrs = node["attributes"]
        node["ranges"] = merged_ranges(node["rangeRows"] if node.get("hasRanges") else
                                       [(attrs["low_pc"], attrs["high_pc"])] if "low_pc" in attrs and "high_pc" in attrs else [])
    return nodes


def code_layout(data):
    assert data[:8] == b"\0asm\1\0\0\0"
    offset, code, declarations = 8, None, None

    def u32():
        nonlocal offset
        value = 0
        for n in range(5):
            assert offset < len(data), "Truncated WASM integer"
            byte = data[offset]
            offset += 1
            assert n < 4 or not byte & 0xf0, "Invalid WASM u32"
            value += (byte & 127) << (7 * n)
            if not byte & 128:
                return value
        raise AssertionError("Invalid WASM u32")

    while offset < len(data):
        tag = data[offset]
        offset += 1
        size = u32()
        start, end = offset, offset + size
        assert end <= len(data), "Truncated WASM section"
        if tag == 2:
            assert u32() == 0, "Imported functions are unsupported"
        elif tag == 3:
            assert declarations is None, "Duplicate function section"
            declarations = u32()
            for _ in range(declarations):
                u32()
            assert offset == end, "Malformed function section"
        elif tag == 10:
            assert code is None, "Duplicate code section"
            count, bodies = u32(), []
            for _ in range(count):
                length = u32()
                assert length and offset + length <= end, "Invalid WASM body"
                bodies.append((offset - start, offset + length - start))
                offset += length
            assert offset == end, "Malformed code section"
            code = (start, bodies)
        offset = end
    assert code and len(code[1]) == declarations, "Incomplete WASM function layout"
    return code


def attribute(nodes, offset, key, visited=()):
    assert offset not in visited, "Cyclic scope origin"
    assert offset in nodes, "Missing scope origin"
    attrs = nodes[offset]["attributes"]
    if key in attrs:
        return attrs[key]
    for link in ("abstract_origin", "specification"):
        if link in attrs:
            value = attribute(nodes, attrs[link], key, visited + (offset,))
            if value is not None:
                return value
    return None


class ScopeIndex:
    def __init__(self, nodes, bodies):
        self.nodes, self.chains, self.events = nodes, {}, {}
        self.stats = {"inlineDIEs": 0, "liveScopes": 0, "deadScopes": 0, "emptyScopes": 0,
                      "discontiguousScopes": 0}
        skipped = set()
        assert bodies and all(a < b for a, b in bodies)
        assert all(bodies[n][1] <= bodies[n+1][0] for n in range(len(bodies)-1)), "Overlapping WASM bodies"
        for offset, node in nodes.items():
            if node["tag"] not in FUNCTIONS:
                continue
            if node["tag"] == "DW_TAG_inlined_subroutine":
                self.stats["inlineDIEs"] += 1
            parent = node["parent"]
            while parent is not None and nodes[parent]["tag"] not in FUNCTIONS:
                parent = nodes[parent]["parent"]
            ranges = node["ranges"]
            if node.get("dead"):
                skipped.add(offset)
                self.stats["deadScopes"] += 1
                continue
            if node["tag"] == "DW_TAG_subprogram":
                if ranges and all(a in (0, 0xffffffff) for a, _ in ranges):
                    skipped.add(offset)
                    self.stats["deadScopes"] += 1
                    continue
                if not ranges:
                    skipped.add(offset)
                    self.stats["emptyScopes"] += 1
                    continue
                containers = [i for i, (a, b) in enumerate(bodies) if all(a <= x < y <= b for x, y in ranges)]
                assert len(containers) == 1, "Function range is not inside one WASM body"
                chain = (offset,)
            else:
                if parent in skipped or not ranges:
                    skipped.add(offset)
                    self.stats["emptyScopes"] += 1
                    continue
                assert parent in self.chains, "Inline scope has no live function ancestor"
                assert all(any(a <= x < y <= b for a, b in nodes[parent]["ranges"]) for x, y in ranges), "Inline scope exceeds parent range"
                chain = self.chains[parent] + (offset,)
            self.chains[offset] = chain
            self.stats["liveScopes"] += 1
            self.stats["discontiguousScopes"] += len(ranges) > 1
            for start, end in ranges:
                self.events.setdefault(start, []).append((offset, 1))
                self.events.setdefault(end, []).append((offset, -1))

    def at(self, positions):
        active, cursor = Counter(), 0
        events = sorted(self.events)
        previous = -1
        for position in positions:
            assert position > previous, "Unordered scope lookup"
            previous = position
            while cursor < len(events) and events[cursor] <= position:
                for offset, delta in self.events[events[cursor]]:
                    active[offset] += delta
                    assert active[offset] >= 0, "Unbalanced scope interval"
                    if not active[offset]:
                        del active[offset]
                cursor += 1
            chains = {self.chains[offset] for offset in active}
            leaves = tuple(sorted(c for c in chains if not any(len(other) > len(c) and other[:len(c)] == c for other in chains)))
            yield leaves
