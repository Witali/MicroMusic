"""Current-source build identity and read-only exact playback evidence reuse.

Factored from the frozen V1 admission proof for subsequent private admission
jobs; the already recorded V1 helpers/receipts remain unchanged.
"""
from pathlib import Path
import json
from admit import sha


class PlayerEvidence:
    def __init__(self, epoch, prepared):
        self.epoch = epoch
        self.player, self.bench = epoch.player, epoch.bench
        self.avr, self.runner, self.lib = map(Path, (prepared['avr_bin'], prepared['runner'], prepared['lib']))
        self.wsl = prepared['wsl']
        self.env = self.bench.environment(epoch.active, self.avr, True, harness=self.player.EXAMPLE / 'player.cpp', required_symbols=(), retained_symbols=())
        self.env['settings'] = {**self.env['settings'], 'queue': 256, 'prefill': 192}
        assert self.env['dependencies'] == prepared['build_environment']['dependencies']
        assert self.env['source_sha256'] == prepared['decoder_source_sha256']
        self.validation = self.bench.validation_provenance(self.runner, self.lib, self.wsl,
            sources=(Path(self.player.__file__), self.player.VALIDATION / 'sim_player.c', self.player.VALIDATION / 'player_hardware.cpp', self.player.EXAMPLE / 'player_config.h'))
        self.validation['runner_sources'] = {'sim_player.c': self.bench.digest(self.player.VALIDATION / 'sim_player.c')}
        assert self.validation['runtime'] == prepared['validation']['runtime']
        self.proof = sha(self.bench.canonical([self.bench.artifact_provenance(self.avr), self.bench.digest(Path(self.player.__file__))]))

    def recipe(self, streams, irq):
        from measure_speech_firmware import voice_header
        flags = self.bench.command_flags(self.env, self.bench.CANDIDATES['unroll1-tune0-lto-call-relax'], True, irq)
        flags = [f for f in flags if not f.startswith(('-DLPX4_PROFILE_QUEUE=', '-DLPX4_PROFILE_PREFILL=', '-DLPX4_PROFILE_IRQ_LOAD='))]
        flags += ['-DLPX_PLAYER_QUEUE=256', '-DLPX_PLAYER_PREFILL=192', '-DLPX_PLAYER_IRQ_LOAD=' + str(irq), '-DLPX_PLAYER_DATA_HEADER="voice_data.h"']
        suffix = '#define LPX_PLAYER_SEGMENTS %d\n' % len(streams)
        header = voice_header(streams).replace('profile_', 'lpx_') + suffix
        layout = voice_header([b'' for _ in streams]).replace('profile_', 'lpx_') + suffix
        recipe = {'environment': self.bench.build_provenance(self.env), 'compiler_options': flags,
            'player_config_sha256': self.bench.digest(self.player.EXAMPLE / 'player_config.h'), 'voice_layout_sha256': sha(layout.encode()),
            'declared_segment_samples': [int.from_bytes(b[8:12], 'little') for b in streams]}
        build_id = sha(self.bench.canonical(recipe))
        image_id = sha(self.bench.canonical([build_id, [sha(b) for b in streams], sha(header.encode())]))
        return build_id, image_id, flags

    def reuse(self, row, streams, expected, irq):
        folder = Path(row['output'])
        cache = json.loads((folder / 'cost.json').read_text())
        verified = json.loads((folder / 'verification.json').read_text())
        cost = cache['cost']
        build_id, image_id, flags = self.recipe(streams, irq)
        assert cache['fingerprint'] == image_id and cache['proof_fingerprint'] == self.proof
        assert cache['cost_sha256'] == sha(self.bench.canonical(cost))
        assert cost['build_fingerprint'] == build_id and cost['compiler_options'] == flags
        assert cost['environment'] == self.env and cost['source_fingerprint'] == sha(self.bench.canonical(self.env['source_sha256']))
        assert cost['stream_sha256'] == [sha(blob) for blob in streams]
        assert cost == verified['cost'] == row['verification']['cost']
        for name, key in (('player.elf', 'image_sha256'), ('program.bin', 'binary_sha256'), ('player.hex', 'hex_sha256')):
            assert self.bench.digest(folder / name) == cost[key]
        self.player.checked_image(folder, self.avr, streams, 256)
        assert verified['validation_provenance'] == self.validation
        fingerprint = sha(self.bench.canonical([self.validation, cost['image_sha256'], self.bench.digest(folder / 'observer.txt'), sha(expected), 0]))
        assert verified['fingerprint'] == fingerprint
        actual = (folder / 'valid.pcm8').read_bytes()
        report = json.loads((folder / 'observer.json').read_text())
        assert self.bench.digest(folder / 'observer.json') == verified['report_sha256'] and sha(actual) == verified['pwm_sha256']
        assert report == verified['report'] and actual == expected
        assert self.player.validate(report, actual, expected) and verified['passed'] and cost['flash_bytes'] <= 32768
        return verified, folder

    def verify_recipe(self, cost, streams, irq):
        build_id, _, flags = self.recipe(streams, irq)
        assert cost['build_fingerprint'] == build_id and cost['compiler_options'] == flags
        assert cost['source_fingerprint'] == sha(self.bench.canonical(self.env['source_sha256']))
        assert cost['stream_sha256'] == [sha(blob) for blob in streams]
