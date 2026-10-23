"""Store/recover LPX3 without changing any excitation or synthesized sample."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ATtiny13A/Sound/codec'))
from lpx3_entropy import pack, unpack


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('input',type=Path)
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--decode',action='store_true')
    a = p.parse_args()
    source = a.input.read_bytes()
    if a.decode:
        output = unpack(source)
        report = dict(operation='restore-original-LPX3',bytes=len(output))
    else:
        output,report = pack(source)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_bytes(output)
    report.update(input_sha256=hashlib.sha256(source).hexdigest(),
                  output_sha256=hashlib.sha256(output).hexdigest())
    print(json.dumps(report))


if __name__ == '__main__':
    main()
