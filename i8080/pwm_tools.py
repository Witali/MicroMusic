"""Authoring helpers for documented 8080 INTE PWM, with exact edge deadlines.

Register state is never changed by delay padding. ORI 0 is permitted only when
Z is dead: these templates read only Z, never incoming CY or another PSW bit.
The explicit z_live_out contract preserves Z across a kernel boundary when
requested. Hardware INT/WAIT/HOLD are off.
"""
from functools import lru_cache
from pathlib import Path
import importlib.util
import json

ROOT = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


legacy = load('pwm_legacy', ROOT/'Sound/dual-crc-voice/build.py')
Code = legacy.Code


def ins(cost, text, *op, target=None):
    return cost, text, op, target


def jump(target, mnemonic='JMP', opcode=0xc3):
    return ins(10, mnemonic+' '+target, opcode, 0, 0, target=target)


@lru_cache(None)
def delay(t, z_dead=False):
    if t == 0:
        return ()
    candidates = []
    choices = [ins(4, 'NOP', 0), ins(5, 'MOV A,A', 0x7f)]
    if z_dead:
        choices.append(ins(7, 'ORI 000H', 0xf6, 0))
    for action in choices:
        if t >= action[0]:
            rest = delay(t-action[0], z_dead)
            if rest is not None:
                candidates.append((action,)+rest)
    return min(candidates, key=lambda seq: sum(len(a[2]) for a in seq)) if candidates else None


def size(tree):
    return sum(len(a[2]) for a in tree[0])+sum(size(c) for _, c in tree[1])


def needs_z(actions, children, live_out=False):
    for action in actions:
        opcode = action[2][0]
        if opcode in (0xc2, 0xca):
            return True
        if opcode in (0x1d, 0x3d, 0xb7, 0xb5, 0xe6, 0xf6):
            return False
    return any(needs_z(*child, live_out) for _, child in children) if children else live_out


def schedule(tree, width, period, repeats=1, entry_limit=None, z_live_out=False):
    edges = []
    for pulse in range(repeats):
        if pulse:
            edges.append((pulse*period, ins(4, 'EI', 0xfb)))
        if width:
            edges.append((pulse*period+width, ins(4, 'DI', 0xf3)))

    @lru_cache(None)
    def visit(actions, children, now, edge, budget):
        options = []
        if not actions:
            if children:
                parts = tuple((label, visit(*child, now, edge, budget)) for label, child in children)
                if all(child is not None for _, child in parts):
                    options.append(((), parts))
        elif len(actions) == 1 and not children:
            fill = delay(repeats*period-now-actions[0][0], not z_live_out) if edge == len(edges) else None
            if fill is not None:
                options.append((fill+actions, ()))
        else:
            action = actions[0]
            deadline = edges[edge][0] if edge < len(edges) else repeats*period
            used = budget+len(action[2]) if budget >= 0 else -1
            if now+action[0] <= deadline and (used < 0 or used <= entry_limit):
                if budget >= 0 and action[1].startswith('JMP '):
                    used = -1
                rest = visit(actions[1:], children, now+action[0], edge, used)
                if rest is not None:
                    options.append(((action,)+rest[0], rest[1]))
        if edge < len(edges) and (actions or not children):
            deadline, action = edges[edge]
            fill = delay(deadline-now, not needs_z(actions, children, z_live_out))
            if fill is not None:
                used = budget+sum(len(a[2]) for a in fill)+1 if budget >= 0 else -1
                rest = visit(actions, children, deadline+4, edge+1, used) if used < 0 or used <= entry_limit else None
                if rest is not None:
                    options.append((fill+(action,)+rest[0], rest[1]))
        return min(options, key=size) if options else None

    result = visit(*tree, 4, 0, 1 if entry_limit else -1)
    return None if result is None else ((ins(4, 'EI' if width else 'DI', 0xfb if width else 0xf3),)+result[0], result[1])


def emit(code, tree):
    for _, text, op, target in tree[0]:
        code.emit(text, *op)
        if target:
            code.fixups.append((len(code.data)-2, target))
    for label, child in tree[1]:
        if label:
            code.label(label)
        emit(code, child)


def split_entry(tree):
    at = next(i for i, a in enumerate(tree[0]) if a[1].startswith('JMP '))+1
    return (tree[0][:at], ()), (tree[0][at:], tree[1])


class Allocator:
    def __init__(self, available):
        self.available = set(available)

    def reserve(self, start, size):
        assert all(at in self.available for at in range(start, start+size)), hex(start)
        self.available.difference_update(range(start, start+size))

    def spans(self):
        spans = []
        for at in sorted(self.available):
            if spans and spans[-1][1] == at:
                spans[-1][1] += 1
            else:
                spans.append([at, at+1])
        return spans

    def place(self, code):
        start = next(lo for lo, hi in self.spans() if hi-lo >= len(code.data))
        code.labels = {key: value+start-code.origin for key, value in code.labels.items()}
        code.origin = start
        self.reserve(start, len(code.data))


def save(root, name, data, check=False):
    if isinstance(data, dict):
        data = json.dumps(data, ensure_ascii=False, indent=2)+'\n'
    if isinstance(data, str):
        data = data.encode('utf-8')
    data = bytes(data)
    if check:
        actual = (root/name).read_bytes()
        if Path(name).suffix in ('.json', '.asm'):
            actual = actual.replace(b'\r\n', b'\n')
        assert actual == data, f'Stale: {root/name}'
    else:
        root.mkdir(parents=True, exist_ok=True)
        (root/name).write_bytes(data)
