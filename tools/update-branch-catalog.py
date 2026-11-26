"""Refresh docs/BRANCHES.md from local Git refs, preserving edited descriptions.

This does not fetch, check out, merge or push anything. Run in the main worktree
and commit the resulting documentation change separately from implementation.
"""
import argparse
import datetime
from pathlib import Path
import re
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--date', default=datetime.date.today().isoformat())
    args = parser.parse_args()
    datetime.date.fromisoformat(args.date)
    root = Path(subprocess.check_output(['git', 'rev-parse', '--show-toplevel'], text=True).strip())
    branch = subprocess.check_output(['git', 'branch', '--show-current'], cwd=root, text=True).strip()
    if branch != 'main':
        parser.error('Run in the existing main worktree')
    path = root / 'docs/BRANCHES.md'
    descriptions = {}
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            match = re.match(r'^\| `([^`]+)` \| [^|]+ \| (.*) \|$', line)
            if match:
                descriptions[match[1]] = match[2]
    defaults = {
        'main': 'Integrated project baseline and GitHub Pages source.',
        'codex/lpx-lp20-study': 'Retained LP20/LPX-Z80 source history and transfer review; five recovered source snapshots, with current LPX unchanged.',
        'codex/lpx-compact-quality': 'Experiment: compact P3 listening candidates and small strict 2 kbit/s gains at fixed size; decoder formats unchanged.',
        'codex/lpx-local-noise': 'Experimental source-frozen excitation noise ranking; paired PCM/PWM comparison found no admitted gain.',
        'codex/lpx-pcm-quality': 'Selectable PCM or PWM encoder quality target, with unchanged LPX format and decoder.',
        'codex/lpx-lsf-groups': 'LSF grouping and packing study, AVR tuning checks, and initial Z80 transfer review.',
        'codex/lpx-bfp-trajectories': 'Experimental shared-exponent groups and logarithmic trajectories; compare size, quality and full AVR cost.',
        'codex/lpx-adaptive-order': 'Adaptive LPC order, coefficient precision and compact storage experiments with AVR constraints.',
    }
    for name, description in defaults.items():
        descriptions.setdefault(name, description)
    output = subprocess.check_output(
        ['git', 'for-each-ref', '--format=%(refname)%09%(subject)%09%(symref)',
         'refs/heads', 'refs/remotes'], cwd=root, text=True)
    entries = {}
    for line in output.splitlines():
        ref, subject, symbolic = line.split('\t', 2)
        if symbolic:
            continue
        if ref.startswith('refs/heads/'):
            name, location = ref[len('refs/heads/'):], 'local'
        else:
            remote, name = ref[len('refs/remotes/'):].split('/', 1)
            location = remote
        item = entries.setdefault(name, {'locations': set(), 'subject': subject})
        item['locations'].add(location)
        if location == 'local':
            item['subject'] = subject
    lines = [
        '# Branch catalog', '',
        f'Local snapshot: {args.date}. Covers local branches and remote-tracking refs already present in this clone; no network refresh was performed.', '',
        'Descriptions state the branch purpose when recorded. Other initial descriptions name the latest recorded work; refine them when resuming that branch. Availability in `origin` means a local remote-tracking ref exists and does not certify current server state. A listed branch may be an experiment or retained history; this table does not assert merge or release status.', '',
        'Refresh from the main worktree with `python tools/update-branch-catalog.py --date YYYY-MM-DD`. Edited descriptions are preserved. Update this catalog when branches are created, renamed, deleted or repurposed, and commit the documentation separately.', '',
        f'Branches: {len(entries)}. Symbolic aliases such as `origin/HEAD` are excluded.', '',
        '| Branch | Available refs | Short description |',
        '| --- | --- | --- |',
    ]
    for name, item in sorted(entries.items(), key=lambda pair: (pair[0] != 'main', pair[0])):
        description = descriptions.get(name)
        if description is None:
            description = ('Latest recorded work: ' + item['subject']).replace('|', '\\|').replace('`', "'")
        locations = ', '.join(sorted(item['locations'], key=lambda x: (x != 'local', x)))
        lines.append(f'| `{name}` | {locations} | {description} |')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8', newline='\n')
    print(f'Updated docs/BRANCHES.md: {len(entries)} branches')


if __name__ == '__main__':
    main()
