"""Exercise all guitar envelope levels and clock phases on assembled AVR code."""
from pathlib import Path
import importlib.util
import json
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class GuitarReleaseTests(unittest.TestCase):
    def test_guitar_decay_release_and_tail_banks(self):
        spec = importlib.util.spec_from_file_location('guitar_builder', ROOT / 'tools/build-rhythmic.py')
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        assignments = dict(lead='acoustic-guitar-nylon', keys='acoustic-guitar-nylon', pluck='acoustic-guitar-nylon', percussion='off')
        data = dict(tempo_bpm=126, instruments=assignments, chord_pairs=[['E', 'E']],
                    chord_notes={'E': [64, 40]}, patterns={'A': ['E4:4']}, playlist=['A'])
        source, metadata = builder.engine.specialize(data, builder.bank.describe_assignments(assignments))
        data.update(metadata)
        source = builder.release_engine.specialize(data, source)
        (ROOT / 'build').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / 'build', prefix='guitar-test-') as temporary:
            folder = Path(temporary)
            (folder / 'synth.S').write_text(source, encoding='utf-8')
            (folder / 'config.inc').write_text('.set REST_INDEX, 1\n.set HOLD_INDEX, 2\n.set PLAYLIST_LEN, 1\n.set FIRST_PLAYLIST_INDEX, 0\n.set GRID_STEP_LOW, 0\n.set GRID_STEP_HIGH, 0\n.set GRID_INITIAL_HIGH, 255\n')
            (folder / 'score.inc').write_text('playlist:\n.byte 0\ndurations:\n.byte 1,2,3,4,6,8,16\nnote_steps:\n.byte 0,2\nchord_steps:\n.byte 0,1,0,2\nmelody_data:\nfirst_section:\n.byte 6,255\n')
            rom, labels = builder.release_engine.assemble_relaxed(folder / 'synth.S')
            fixture = folder / 'fixture.json'
            fixture.write_text(json.dumps(dict(rom=list(rom), labels=labels)))
            program = '''
import fs from 'node:fs';
import assert from 'node:assert/strict';
import {AVRCore} from './web-player/lib/avr-core.js';
const {rom,labels}=JSON.parse(fs.readFileSync(process.argv[1]));
const voices=[96,101,106,111,116];let checks=0;
for(let clock=0;clock<256;clock++)for(let level=0;level<16;level++)for(const held of [false,true]){
 const c=new AVRCore(Uint8Array.from(rom),new Uint8Array(64),{fastIdle:false});
 c.r[24]=clock;c.r[1]=100;c.pc=labels.music_tick/2;
 for(let i=0;i<voices.length;i++)c.data[voices[i]]=level|(held?128:0)|[0,16,32,0,32][i];
 let count=0;while(c.pc!==labels['.L0a8']/2){c.step();assert.ok(++count<400);}
 const mask=level<7?7:level<10?3:1;
 const next=Math.max(0,level-Number(!held||!((clock+1)&mask)));
 for(const a of voices){assert.equal(c.data[a]&15,next);checks++;}
 assert.equal(c.r[24],(clock+1)&255);assert.equal(c.sp,159);
}
console.log(checks);
'''
            result = subprocess.run(['node', '--input-type=module', '-e', program, str(fixture)], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(int(result.stdout), 40960)


if __name__ == '__main__':
    unittest.main(verbosity=2)
