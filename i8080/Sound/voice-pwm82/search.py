"""Reproduce the bounded kernel-template search, not a global ISA lower bound."""
import argparse
from pathlib import Path
import importlib.util
spec = importlib.util.spec_from_file_location('fast_voice_build', Path(__file__).resolve().with_name('build.py'))
build = importlib.util.module_from_spec(spec); spec.loader.exec_module(build)


def report():
    candidates = []
    for period in range(73, 110):
        failed, total = [], 0
        for phase in range(5):
            for level in range(16):
                tree = build.program(phase, level, period)
                if tree is None:
                    failed.append([phase, level])
                else:
                    total += build.p.size(tree)
        candidates.append({'period_t': period, 'failed_handlers': failed, 'scheduled_code_bytes': total})
    return {'method': 'All 80 level/phase handlers, fixed two-pulse grid; explicit Z liveness and 8/9-byte entry budget',
            'smallest_complete_period_t_in_tested_templates': min(c['period_t'] for c in candidates if not c['failed_handlers']),
            'global_optimality_proved': False, 'candidates': candidates}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--check', action='store_true')
    args = parser.parse_args(); result = report()
    build.p.save(Path(__file__).resolve().parent, 'SEARCH.json', result, args.check)
    print('Smallest complete tested period:', result['smallest_complete_period_t_in_tested_templates'])
