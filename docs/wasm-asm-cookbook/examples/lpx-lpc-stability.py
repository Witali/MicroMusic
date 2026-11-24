#!/usr/bin/env python3
"""Check the production Schur guard against synthetic independent oracles.

Requires Python with NumPy, Node, and a wasm32-capable Clang/sysroot. From the
repository root, supply the installed paths explicitly:

python docs/wasm-asm-cookbook/examples/lpx-lpc-stability.py \
    --compiler <clang> --sysroot <emscripten-cache-sysroot>

Only the compact JSON summary belongs in retained reports. Generated arrays,
binary and the Node transport stay under ignored build/. No audio input is read
or generated.
"""
from pathlib import Path
import argparse
import json
import math
import subprocess

import numpy as np


def vectors():
    rng = np.random.default_rng(19423)
    rows = []

    def append(coefficients):
        rows.append(np.clip(np.rint(coefficients * 4096), -32767, 32767).astype("<i2"))

    for value in (0, 4095, -4095, 4096, -4096, 8192, -8192, 32767, -32767):
        coefficients = np.zeros(10)
        coefficients[0] = value / 4096
        append(coefficients)
    for value in (4095, -4095, 4096, -4096, 4097, -4097):
        coefficients = np.zeros(10)
        coefficients[-1] = value / 4096
        append(coefficients)
    for _ in range(10000):
        coefficients = np.array([1.])
        for reflection in rng.uniform(-.98, .98, 10):
            coefficients = (np.r_[coefficients, 0]
                            + reflection * np.r_[0, coefficients[::-1]])
        append(coefficients[1:])
    for _ in range(10000):
        append(rng.uniform(-3, 3, 10))
    for _ in range(10000):
        angles = rng.uniform(.03 * np.pi, .97 * np.pi, 5)
        radii = rng.uniform(.2, 1.15, 5)
        poles = radii * np.exp(1j * angles)
        append(np.poly(np.r_[poles, poles.conj()]).real[1:])
    return np.array(rows)


def exact_stability(coefficients):
    """Unnormalized Schur recursion with exact Python integers and GCD scaling.

    This independently resolves near-unit eigenvalue/root estimates. It uses
    neither production floating-point divisions nor the production margin.
    """
    polynomial = [4096] + [int(value) for value in coefficients]
    for order in range(10, 0, -1):
        if abs(polynomial[order]) >= abs(polynomial[0]):
            return False
        previous = [polynomial[0] * polynomial[index]
                    - polynomial[order] * polynomial[order - index]
                    for index in range(order)]
        divisor = math.gcd(*previous)
        polynomial = [value // divisor for value in previous]
    return True


def run(command, stage):
    try:
        result = subprocess.run(command, capture_output=True, check=False)
    except OSError:
        raise SystemExit(f"Could not launch {stage}.") from None
    if result.returncode:
        # Keep local toolchain paths and inherited environment out of receipts.
        raise SystemExit(f"{stage} failed with exit code {result.returncode}.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", required=True)
    parser.add_argument("--sysroot", required=True)
    parser.add_argument("--node", default="node")
    args = parser.parse_args()
    repository = Path(__file__).resolve().parents[3]
    output = repository / "build/lpx-lpc-stability"
    output.mkdir(parents=True, exist_ok=True)
    source = Path(__file__).with_suffix(".cpp").resolve()
    binary = output / "guard.wasm"
    sysroot = Path(args.sysroot).resolve()
    run([args.compiler, "--target=wasm32-unknown-unknown", "-O3", "-std=c++11",
         "-ffp-contract=off", "-ffreestanding", "-nostdlib", f"--sysroot={sysroot}",
         "-isystem", str(sysroot / "include"), "-Wl,--no-entry",
         "-Wl,--export-memory", "-Wl,--export=stability_input",
         "-Wl,--export=stability_test", "-Wl,--initial-memory=131072",
         str(source), "-o", str(binary)], "wasm32 compilation")
    cases = vectors()
    input_path, label_path = output / "cases.i16", output / "labels.u8"
    cases.tofile(input_path)
    runner = output / "run.mjs"
    runner.write_text("""import {readFileSync,writeFileSync} from 'node:fs';
const [binary,cases,output]=process.argv.slice(2);
const {instance}=await WebAssembly.instantiate(readFileSync(binary));
const api=instance.exports,rows=readFileSync(cases),labels=new Uint8Array(rows.length/20);
const input=new Int16Array(api.memory.buffer,api.stability_input(),10);
for(let i=0;i<labels.length;++i){input.set(new Int16Array(rows.buffer,rows.byteOffset+i*20,10));labels[i]=api.stability_test();}
writeFileSync(output,labels);
""", encoding="utf-8")
    run([args.node, str(runner), str(binary), str(input_path), str(label_path)], "WASM check")
    labels = np.fromfile(label_path, dtype="u1").astype(bool)
    radii = np.array([np.abs(np.roots(np.r_[1., row / 4096])).max() for row in cases])
    ambiguity = 1e-7
    stable = radii < 1 - ambiguity
    unstable = radii > 1 + ambiguity
    boundary = ~(stable | unstable)
    exact = np.array([exact_stability(row) for row in cases[boundary]])
    predicted = labels[boundary]
    report = {
        "schema": "lpx-lpc-stability-synthetic-validation-v1",
        "seed": 19423,
        "cases": len(cases),
        "numpy": np.__version__,
        "productionReflectionMargin": 1e-9,
        "numpyRootAmbiguity": ambiguity,
        "stableFar": int(stable.sum()),
        "unstableFar": int(unstable.sum()),
        "falseAcceptsFar": int((unstable & labels).sum()),
        "falseRejectsFar": int((stable & ~labels).sum()),
        "boundaryCases": int(boundary.sum()),
        "boundaryExactlyStable": int(exact.sum()),
        "boundaryUnstableOrMarginal": int((~exact).sum()),
        "falseAcceptsBoundary": int((predicted & ~exact).sum()),
        "falseRejectsBoundary": int((~predicted & exact).sum()),
        "analyticalCasesPassed": labels[:15].astype(int).tolist()
        == [1, 1, 1, 0, 0, 0, 0, 0, 0, 1, 1, 0, 0, 0, 0],
    }
    report["passed"] = (report["analyticalCasesPassed"]
                        and not any(report[key] for key in (
                            "falseAcceptsFar", "falseRejectsFar",
                            "falseAcceptsBoundary", "falseRejectsBoundary")))
    (output / "summary.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
