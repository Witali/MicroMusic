"""Current-epoch private player admission; prepare is safe before asset handoff.

All LPX imports come from --source-root. Generated receipts and media stay under
that root's ignored build/. This dispatcher contains no corpus paths or IDs.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys

sha = lambda data: hashlib.sha256(data).hexdigest()
canonical = lambda value: json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


class Epoch:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.active = self.root / 'Codecs/LPX/01_ACTIVE_Q0_CODEC'
        self.tools = self.active / 'tools'
        if not (self.tools / 'build_release_player.py').is_file():
            raise ValueError('Expected a current LPX source root')
        os.chdir(self.root)
        sys.path.insert(0, str(self.tools))
        self.modules = {name: importlib.import_module(name) for name in (
            'benchmark_speech_flash', 'build_release_player', 'build_release_observer',
            'batch_decoder', 'speech_compact', 'standard_metrics', 'output_paths')}
        self.verify_imports()
        if self.modules['build_release_player'].REPOSITORY.resolve() != self.root or self.modules['batch_decoder'].ROOT.resolve() != self.active:
            raise ValueError('Builder/native decoder belongs to a different source epoch')
        self.bench = self.modules['benchmark_speech_flash']
        self.player = self.modules['build_release_player']
        self.observer = self.modules['build_release_observer']

    def verify_imports(self):
        for path in self.tools.glob('*.py'):
            module = sys.modules.get(path.stem)
            if module is not None and getattr(module, '__file__', None) and Path(module.__file__).resolve() != path.resolve():
                raise ValueError('LPX module imported from a different source epoch: ' + path.stem)

    def snapshot(self):
        self.verify_imports()
        files = [*(self.active / 'src').rglob('*'), *self.tools.glob('*.py'),
                 *self.player.EXAMPLE.glob('*'), self.player.VALIDATION / 'sim_player.c',
                 self.player.VALIDATION / 'player_hardware.cpp']
        return {path.relative_to(self.root).as_posix(): sha(path.read_bytes()) for path in sorted(files) if path.is_file()}

    def output(self, path):
        path = Path(path).resolve()
        build = (self.root / 'build').resolve()
        if path == build or not path.is_relative_to(build):
            raise ValueError('Admission outputs must stay in the source epoch ignored build/')
        if path.is_symlink() or path.exists() and path.is_file() and path.stat().st_nlink > 1:
            raise ValueError('Admission output alias')
        return path

    def save(self, path, value):
        path = self.output(path)
        temporary = path.with_suffix('.writing')
        self.output(temporary)
        self.modules['output_paths'].protect_outputs([Path(__file__), *[self.root / name for name in self.snapshot()]], [path, temporary])
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n', encoding='utf-8', newline='\n')
        temporary.replace(path)

    def prepare(self, args):
        folder = self.output(args.output)
        before = self.snapshot()
        runner = self.observer.build(folder / 'observer', args.include, args.lib, wsl=args.wsl)
        env = self.bench.environment(self.active, args.avr_bin, True, harness=self.player.EXAMPLE / 'player.cpp', required_symbols=(), retained_symbols=())
        env['settings'] = {**env['settings'], 'queue': 256, 'prefill': 192}
        validation = self.bench.validation_provenance(runner, args.lib, args.wsl,
            sources=(Path(__file__), self.player.VALIDATION / 'sim_player.c', self.player.VALIDATION / 'player_hardware.cpp'))
        if self.snapshot() != before:
            raise ValueError('Source epoch changed during observer/dependency preparation')
        receipt = {'schema': 'lpx-quiet-voice-player-preparation-private-v1',
                   'source_root': str(self.root), 'source_commit_at_prepare': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
                   'source_inventory': before, 'source_inventory_sha256': sha(canonical(before)),
                   'dispatcher_sha256': sha(Path(__file__).read_bytes()),
                   'decoder_source_sha256': self.bench.source_hashes(self.active / 'src'),
                   'build_environment': env, 'validation': validation,
                   'runner': str(runner), 'avr_bin': str(Path(args.avr_bin).resolve()),
                   'include': str(Path(args.include).resolve()), 'lib': str(Path(args.lib).resolve()), 'wsl': args.wsl,
                   'queue': 256, 'prefill': 192, 'irq_loads': [0, 100],
                   'target_images_built': 0, 'playback_measurements': 0,
                   'source_epoch_imports_verified': True,
                   'scope': 'Observer/dependency preparation only; no asset selection, target build, quality or playback admission.'}
        self.save(folder / 'preparation-private.json', receipt)
        return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare',))
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    for name in ('avr-bin', 'include', 'lib'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--wsl')
    args = parser.parse_args()
    receipt = Epoch(args.source_root).prepare(args)
    print(json.dumps({'status': 'observer and epoch prepared', 'source_epoch_imports_verified': receipt['source_epoch_imports_verified'],
                      'target_images_built': 0, 'playback_measurements': 0}))


if __name__ == '__main__':
    main()
