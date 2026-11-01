"""Carry validated preopt DWARF inline-stack candidates through Binaryen.

Offline metadata only. This does not measure exclusive subsystem durations.
"""
import argparse
from bisect import bisect_right
from collections import Counter
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import posixpath
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


LABELS = load_module("micromusic_source_labels", ROOT / "web-player/scripts/probe-source-map-labels.py")
SCOPES = load_module("micromusic_dwarf_scopes", ROOT / "web-player/scripts/lib/avr_dwarf_scopes.py")


def project_path(raw, line, sources):
    if not isinstance(raw, str) or not isinstance(line, int):
        return None
    raw = raw.replace("\\", "/")
    anchor = "web-player/native/"
    at = raw.find(anchor)
    if at < 0 or (at and raw[at-1] != "/"):
        return None
    path = posixpath.normpath(raw[at:])
    return path if path in sources and 1 <= line <= sources[path] else None


def frame(offset, nodes, sources):
    get = lambda key: SCOPES.attribute(nodes, offset, key)
    name, raw, line = get("name"), get("decl_file"), get("decl_line")
    path = project_path(raw, line, sources)
    valid_name = isinstance(name, str) and re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", name)
    project_claim = isinstance(raw, str) and "web-player/native/" in raw.replace("\\", "/")
    result = {"kind": "project" if path and valid_name else "support" if raw and valid_name and not project_claim else "unresolved"}
    if result["kind"] == "project":
        result.update(function=name, source=path, line=line)
    attrs = nodes[offset]["attributes"]
    call_line = attrs.get("call_line")
    call_file = project_path(attrs.get("call_file"), call_line, sources)
    if call_file:
        result["callsite"] = {"source": call_file, "line": call_line}
    return result


def scope_map(original, index, base, bodies):
    rows = LABELS.decode_map(original)
    assert len(set(original["sources"])) == len(original["sources"]), "Duplicate source-file identities"
    originals = {r["offset"]: r for r in rows}
    points = sorted(set(originals) | {base+p for p in index.events} | {base+p for pair in bodies for p in pair})
    queried = [p for p in points if p >= base]
    stacks = dict(zip(queried, index.at(p-base for p in queried)))
    starts = [a+base for a, _ in bodies]

    def body_at(point):
        n = bisect_right(starts, point)-1
        return n if n >= 0 and point < bodies[n][1]+base else None

    contexts, interned, segments, names, expected = [], {}, [], [], {}
    source_ids = {s: n for n, s in enumerate(original["sources"])}
    offset = source = line = column = name = 0
    previous = None
    mapped = carried = 0
    for point in points:
        if point in originals:
            previous = originals[point]
            position = previous["position"]
        else:
            position = previous["position"] if previous and body_at(point) is not None and body_at(previous["offset"]) == body_at(point) else None
            carried += position is not None
        fields = [point-offset]
        offset = point
        if position is not None:
            mapped += 1
            chains = stacks.get(point, ())
            if chains not in interned:
                interned[chains] = len(contexts)
                contexts.append({"kind": "unique" if len(chains) == 1 else "ambiguous" if chains else "unresolved",
                                 "chains": chains})
                names.append("micromusic-inline-" + str(interned[chains]))
            token = interned[chains]
            label = names[token]
            expected.setdefault(label, set()).add(position)
            _, file, next_line, next_column = position
            next_source = source_ids[file]
            fields += [next_source-source, next_line-line, next_column-column, token-name]
            source, line, column, name = next_source, next_line, next_column, token
        segments.append("".join(LABELS.vlq(v) for v in fields))
    return {**original, "names": names, "mappings": ",".join(segments)}, contexts, expected, {
        "originalMappedPositions": sum(r["position"] is not None for r in rows),
        "expandedMappedPositions": mapped, "carriedBoundaryPositions": carried}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("input", "source-map", "emsdk", "out-dir"):
        parser.add_argument("--" + option, required=True, type=Path)
    parser.add_argument("--em-config", type=Path)
    args = parser.parse_args()
    out = args.out_dir.resolve()
    assert out != ROOT / "build" and (ROOT / "build") in out.parents, "Keep diagnostics in build/"
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").unlink(missing_ok=True)
    sha = lambda data: hashlib.sha256(data).hexdigest()
    manifest = json.loads((ROOT / "web-player/wasm/device-build.json").read_text())
    sources = {}
    for path, expected in manifest["inputs"].items():
        data = (ROOT / path).read_bytes().replace(b"\r\n", b"\n")
        assert sha(data) == expected, "Stale native input"
        if path.startswith("web-player/native/"):
            sources[path] = len(data.splitlines())
    native = (ROOT / "web-player/wasm/attiny13a.wasm").read_bytes()
    assert sha(native) == manifest["artifacts"]["attiny13a.wasm"]
    suffix = ".exe" if os.name == "nt" else ""
    dwarf_tool, optimizer = [args.emsdk / "upstream/bin" / (name+suffix) for name in ("llvm-dwarfdump", "wasm-opt")]
    verify = subprocess.run([str(dwarf_tool), "--verify", str(args.input)], check=True, capture_output=True)
    (out / "dwarf-verification.txt").write_bytes(verify.stdout+verify.stderr)
    dump = subprocess.run([str(dwarf_tool), "--debug-info", str(args.input)], check=True, capture_output=True)
    (out / "preopt-dwarf.txt").write_bytes(dump.stdout)
    nodes = SCOPES.parse_scopes(dump.stdout.decode("utf-8"))
    binary = args.input.read_bytes()
    base, bodies = SCOPES.code_layout(binary)
    index = SCOPES.ScopeIndex(nodes, bodies)
    config = args.em_config or args.source_map.parent / "emscripten-config.py"
    generator = args.emsdk / "upstream/emscripten/tools/wasm-sourcemap.py"
    env = {**os.environ, "EM_CONFIG": str(config.resolve()), "EM_CACHE": str(out / "em-cache"), "PYTHONDONTWRITEBYTECODE": "1"}
    regenerated = out / "regenerated-preopt.map"
    subprocess.run([sys.executable, str(generator), str(args.input), "--dwarfdump", str(dwarf_tool), "-o", str(regenerated)],
                   check=True, capture_output=True, env=env)
    original = json.loads(args.source_map.read_text(encoding="utf-8"))
    assert original == json.loads(regenerated.read_text(encoding="utf-8")), "Input source-map binding differs"
    tagged, contexts, expected, counts = scope_map(original, index, base, bodies)
    frames = {offset: frame(offset, nodes, sources) for offset in index.chains}
    dictionary = {"schema": "micromusic-dwarf-inline-contexts-v1", "contexts": contexts, "frames": frames}
    dictionary_path = out / "inline-contexts.json"
    dictionary_path.write_text(json.dumps(dictionary, separators=(",", ":"))+"\n", encoding="utf-8")
    inp, output, emitted = [out / name for name in ("scoped.input.map", "scoped.wasm", "scoped.output.map")]
    inp.write_text(json.dumps(tagged), encoding="utf-8")
    subprocess.run([str(optimizer), str(args.input), "-O3", "--input-source-map", str(inp), "--output-source-map", str(emitted),
                    "-o", str(output)], check=True, capture_output=True)
    assert LABELS.executable_sections(output.read_bytes()) == LABELS.executable_sections(native), "Executable sections/offsets differ"
    result = LABELS.decode_map(json.loads(emitted.read_text(encoding="utf-8")))
    named, distinct = LABELS.check_labels(result, expected)
    assert named > 0, "No inline context survived"
    surviving = {int(r["name"].removeprefix("micromusic-inline-")) for r in result if r["name"] is not None}
    report = {"schema": "micromusic-native-inline-transport-v1", "inlineScopesExtracted": True,
              "scopeMeaning": "Pre-Binaryen DWARF4 candidates, not a post-optimization dynamic call stack",
              "exclusiveDurationsMeasured": False, "profileSamplesJoined": False, "sourceMapRegenerationEqual": True,
              "llvmDwarfVerified": True, "nativeInputsVerified": len(manifest["inputs"]), "codeBodies": len(bodies),
              "executableSectionsAndOffsetsEqual": True, "scopeDIEs": index.stats, "input": counts,
              "frames": dict(Counter(f["kind"] for f in frames.values())),
              "contexts": dict(Counter(c["kind"] for c in contexts)),
              "maximumInlineDepth": max(len(c)-1 for x in contexts for c in x["chains"]),
              "output": {"mappedPositions": sum(r["position"] is not None for r in result), "namedPositions": named,
                         "distinctContexts": distinct, "contextKinds": dict(Counter(contexts[n]["kind"] for n in surviving))},
              "nativeSha256": sha(native), "inputSha256": sha(binary), "inputMapSha256": sha(args.source_map.read_bytes()),
              "dwarfToolSha256": sha(dwarf_tool.read_bytes()), "optimizerSha256": sha(optimizer.read_bytes()),
              "sourceMapGeneratorSha256": sha(generator.read_bytes()), "emConfigSha256": sha(config.read_bytes()),
              "artifacts": {name: sha((out / name).read_bytes()) for name in ["dwarf-verification.txt", "preopt-dwarf.txt",
                            "regenerated-preopt.map", "inline-contexts.json", "scoped.input.map", "scoped.output.map", "scoped.wasm"]},
              "sourceHashes": {path: sha((ROOT / path).read_bytes().replace(b"\r\n", b"\n")) for path in
                               ["web-player/scripts/map-native-inline-scopes.py", "web-player/scripts/lib/avr_dwarf_scopes.py",
                                "web-player/scripts/probe-source-map-labels.py"]}}
    (out / "report.json").write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
