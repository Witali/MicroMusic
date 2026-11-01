"""Actual saved-row contract; does not decode, fit or refine audio."""
import argparse
import json
from pathlib import Path
import traceback

from saved_inputs import actual_saved_contract


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    owned = Path(__file__).resolve().parents[4]/'build'
    if not args.output.resolve().is_relative_to(owned.resolve()) or args.output.exists():
        parser.error('Use a fresh output under this worktree build directory')
    args.output.mkdir(parents=True)
    try:
        _, result = actual_saved_contract(args.study)
        (args.output/'contract.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(result))
        return 0
    except Exception as exc:
        (args.output/'failure-private.json').write_text(json.dumps(dict(
            exception_type=type(exc).__name__,traceback=traceback.format_exc()),indent=2)+'\n',encoding='utf-8')
        print(json.dumps(dict(status='failed',exception_type=type(exc).__name__)))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
