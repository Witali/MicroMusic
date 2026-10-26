import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { parseIntelHex } from '../../Emulator/formats.mjs';
import { auditAll } from './audit.mjs';
const read = name => readFileSync(new URL(name,import.meta.url));
const json = name => JSON.parse(read(name));
const source = json('../uniform-pwm/source-score.json');

test('Clock-specific music keeps source tempo and pitch, limits source harmonics and retains complete ROM/HEX', () => {
  for (const hz of [2000000,2500000,3500000]) {
    const root = hz===3500000?'':`clocks/${hz}/`, bank=json(root+'bank.json');
    for (const tune of source.tunes) {
      const name=root+tune.name+'-fluid-pwm108',meta=json(name+'.json'),rom=read(name+'.bin');
      assert.equal(meta.cpu_hz,hz); assert.equal(meta.carrier_hz,hz/108);
      assert.equal(meta.sha256,createHash('sha256').update(rom).digest('hex'));
      assert.deepEqual(parseIntelHex(read(name+'.hex').toString()),new Uint8Array(rom));
      assert.ok(meta.used_bytes<=32768);
      let elapsed=0,frames=0;
      for (let i=0;i<tune.notes.length;i++) {
        const old=tune.notes[i],now=meta.notes[i]; elapsed+=old.duration_t;frames+=now.frames;
        assert.ok(Math.abs(frames*432/hz-elapsed/source.cpu_hz)<=216/hz+1e-12,'cumulative rounding bounded to half a frame');
        for (let channel=0;channel<2;channel++) {
          if (old.steps[channel]===null) { assert.equal(now.steps[channel],null); continue; }
          // The final group has a shorter control-flow tail. The original
          // phase advance per whole note uses its measured mean group time.
          const expected=old.steps[channel]*source.cpu_hz/(old.duration_t/old.groups)/65536;
          const actual=now.steps[channel]*hz/432/65536;
          const cents=1200*Math.log2(actual/expected);
          assert.ok(Math.abs(actual-expected)<=hz/(432*65536*2)+1e-12,'DDS rounded to the closest 16-bit step');
          assert.ok(Math.abs(cents)<(hz===3500000?1.4:1),'DDS pitch error < 1 cent at lower clocks, < 1.4 across all clocks');
          assert.ok(Math.abs(cents-now.pitch_error_cents[channel])<1e-9);
          const midi=Math.round(69+12*Math.log2(expected/440));
          const register=channel?2:+(midi>=bank.piano_register_split_midi);
          assert.ok(actual*bank.banks[register].harmonics<hz/432/2,'source harmonics below synthesis Nyquist before PCM4 quantization');
        }
      }
      assert.equal(meta.frames,frames);
      assert.equal(meta.chunks.reduce((sum,c)=>sum+c.frames,0),frames);
    }
  }
});

test('Full 2 / 2.5 MHz music ROM output matches portable C and every 108T slot, including zero levels and EOF',async () => {
  for (const hz of [2000000,2500000])
    assert.deepEqual(await auditAll(hz),json(`clocks/${hz}/AUDIT.json`));
});
