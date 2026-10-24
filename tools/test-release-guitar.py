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
        (ROOT / 'build').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / 'build', prefix='guitar-test-') as temporary:
            folder = Path(temporary)
            (folder / 'config.inc').write_text('.set REST_INDEX, 1\n.set HOLD_INDEX, 2\n.set PLAYLIST_LEN, 1\n.set FIRST_PLAYLIST_INDEX, 0\n.set GRID_STEP_LOW, 0\n.set GRID_STEP_HIGH, 0\n.set GRID_INITIAL_HIGH, 255\n')
            (folder / 'score.inc').write_text('playlist:\n.byte 0\ndurations:\n.byte 1,2,3,4,6,8,16\nnote_steps:\n.byte 0,2\nchord_steps:\n.byte 0,1,0,2\nmelody_data:\nfirst_section:\n.byte 6,255\n')
            fixtures = []
            for keys, bass in [('acoustic-guitar-nylon', 'acoustic-guitar-nylon'), ('acoustic-grand-piano-soft', 'fretless-bass'), ('acoustic-guitar-nylon', 'fretless-bass')]:
                assignments = dict(lead='acoustic-guitar-nylon', keys=keys, pluck=bass, percussion='off')
                data = dict(tempo_bpm=126, instruments=assignments, chord_pairs=[['E', 'E']],
                            chord_notes={'E': [64, 40]}, patterns={'A': ['E4:4']}, playlist=['A'])
                source, metadata = builder.engine.specialize(data, builder.bank.describe_assignments(assignments))
                data.update(metadata)
                source = builder.release_engine.specialize(data, source)
                (folder / 'synth.S').write_text(source, encoding='utf-8')
                rom, labels = builder.release_engine.assemble_relaxed(folder / 'synth.S')
                fixtures.append(dict(rom=list(rom), labels=labels,
                    masks=[data[r+'_decay_mask'] for r in ('lead','keys','pluck')], piano=keys!='acoustic-guitar-nylon'))
            fixture = folder / 'fixture.json'
            fixture.write_text(json.dumps(fixtures))
            program = '''
import fs from 'node:fs';
import assert from 'node:assert/strict';
import {AVRCore} from './web-player/lib/avr-core.js';
const fixtures=JSON.parse(fs.readFileSync(process.argv[1]));
const voices=[96,101,106,111,116];let checks=0;
for(const {rom,labels,masks,piano} of fixtures){
for(let clock=0;clock<256;clock++)for(let level=0;level<16;level++)for(const held of [false,true]){
 const c=new AVRCore(Uint8Array.from(rom),new Uint8Array(64),{fastIdle:false});
 c.r[24]=clock;c.r[1]=100;c.pc=labels.music_tick/2;
 const banks=[0,1,2,1,2];
 for(let i=0;i<voices.length;i++)c.data[voices[i]]=level|(held?128:0)|(banks[i]*16)|(piano&&banks[i]===1?64:0);
 let count=0;while(c.pc!==labels['.L0a8']/2){c.step();assert.ok(++count<400);}
 for(let i=0;i<voices.length;i++){
   let mask=masks[banks[i]];if(level<10)mask=mask*2+1;if(level<7)mask=mask*2+1;
   const decrement=held?Number(!((clock+1)&mask)):(piano&&banks[i]===1?2:1);
   assert.equal(c.data[voices[i]]&15,Math.max(0,level-decrement));checks++;
 }
 assert.equal(c.r[24],(clock+1)&255);assert.equal(c.sp,159);
}
}
console.log(checks);
'''
            result = subprocess.run(['node', '--input-type=module', '-e', program, str(fixture)], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(int(result.stdout), 122880)


if __name__ == '__main__':
    unittest.main(verbosity=2)
