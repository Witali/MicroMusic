import test from 'node:test';
import assert from 'node:assert/strict';
import { StreamingAudio } from '../stream-audio.mjs';
import { processAudio } from '../formats.mjs';
import { AudioBus } from '../core8080.mjs';

const raw = Float32Array.from({ length: 9600 }, (_, i) => 0.5 + 0.25 * Math.sin(i * 2 * Math.PI * 1000 / 96000));
test('Live audio equals shared WAV processing at 96 kHz, including chunk boundaries', () => {
  const stream = new StreamingAudio(96000, { cutoff: 4500, poles: 4, normalize: true, volume: 1 });
  stream.push(raw.slice(0, 17)); stream.push(raw.slice(17, 1234)); stream.push(raw.slice(1234)); stream.finished = true;
  const data = new Float32Array(raw.length + 4); stream.render(data);
  const reference = processAudio(raw, 96000, 4500, 4, true);
  for (let i = 0; i < raw.length; i++) assert.ok(Math.abs(data[i] - reference[i]) < 1e-6, `sample ${i}`);
  assert.ok(stream.ended); assert.equal(stream.seconds, raw.length / 96000);
});
test('96 kHz source resamples to device rates, preserves duration, and drains its queue', () => {
  for (const deviceRate of [44100, 48000, 96000, 192000]) {
    const stream = new StreamingAudio(deviceRate, { normalize: false, volume: 1 });
    stream.push(raw); stream.finished = true;
    let frames = 0;
    while (!stream.ended && frames < deviceRate) { const block = new Float32Array(128); stream.render(block); for (const sample of block) assert.ok(Number.isFinite(sample) && Math.abs(sample) <= 1); frames += block.length; }
    assert.ok(stream.ended); assert.ok(Math.abs(frames - deviceRate * 0.1) <= 128);
    assert.equal(stream.chunks.length, 0); assert.equal(stream.sourceFrames, raw.length);
  }
});
test('Temporary starvation yields silence and resumes without reordering source samples', () => {
  const stream = new StreamingAudio(96000, { normalize: false, volume: 1 });
  const silence = new Float32Array(128).fill(1); stream.render(silence); assert.ok(silence.every(v => v === 0));
  stream.push(raw.slice(0, 200)); const first = new Float32Array(300); stream.render(first);
  stream.push(raw.slice(200)); stream.finished = true;
  const rest = new Float32Array(raw.length); stream.render(rest);
  const reference = processAudio(raw, 96000, 4500, 4, false);
  for (let i = 0; i < 199; i++) assert.ok(Math.abs(first[i] - reference[i]) < 1e-6);
  for (let i = 199; i < first.length; i++) assert.equal(first[i], 0);
  for (let i = 0; i < raw.length - 199; i++) assert.ok(Math.abs(rest[i] - reference[i + 199]) < 1e-6);
  assert.ok(stream.ended);
});
test('Volume and filter configuration update the active audio stream', () => {
  const a = new StreamingAudio(96000, { normalize: false, volume: 0 }); a.push(raw); a.finished = true;
  const output = new Float32Array(128); a.render(output); assert.ok(output.every(v => v === 0));
  a.volume = 1; a.render(output); assert.ok(output.some(v => Math.abs(v) > 0.01));
  a.configure({ cutoff: 0, poles: 1, normalize: true, volume: 0.3 }); assert.equal(a.volume, 0.3);
});

test('Unfiltered 109T PWM at constant level 8 does not create a 330Hz hum at normal volume', () => {
  const hz = 3500000, period = 109, rate = 96000, deviceRate = 48000;
  const end = Math.floor(hz*1.5/period)*period, audio = new AudioBus(hz, rate, 'inte', 2);
  for (let t = 0; t < end; t += period) { audio.edge(1, t); audio.edge(0, t+36); }
  const source = audio.finish(end);
  const stream = new StreamingAudio(deviceRate, { rate, cutoff: 0, poles: 1, normalize: false, volume: 0.65 });
  stream.push(source); stream.finished = true;
  const output = new Float32Array(deviceRate*1.5); stream.render(output);
  // No audio modulation: this tone is a nonlinear artifact of clipping the
  // integrated carrier BEFORE volume. Windowing excludes the startup transient.
  const frequency = 3*hz/period-rate, start = deviceRate/4, count = deviceRate;
  let re = 0, im = 0, weight = 0, peak = 0;
  for (let i = 0; i < count; i++) {
    const window = 0.5-0.5*Math.cos(2*Math.PI*i/(count-1)), sample = output[start+i];
    const phase = 2*Math.PI*frequency*i/deviceRate;
    re += sample*window*Math.cos(phase); im -= sample*window*Math.sin(phase); weight += window;
    peak = Math.max(peak, Math.abs(sample));
  }
  const amplitude = 2*Math.hypot(re, im)/weight;
  assert.ok(amplitude < 0.001, `Unexpected ${frequency.toFixed(3)}Hz component: ${amplitude}`);
  assert.ok(peak > 0.8 && peak < 1, 'The carrier stays linear with available output headroom');
});

test('Output limiting follows volume and resampling, preserving quiet transients and bounding full-scale output', () => {
  const source = new Float32Array(2100); source.fill(1, 100, 1100);
  for (const volume of [0.25, 1]) {
    const stream = new StreamingAudio(96000, { cutoff: 0, normalize: false, volume });
    stream.push(source); stream.finished = true;
    const output = new Float32Array(source.length+4); stream.render(output);
    assert.ok(output.every(v => Number.isFinite(v) && Math.abs(v) <= 1));
    const peak = Math.max(...output);
    if (volume === 0.25) assert.ok(peak > 0.49 && peak < 0.5, 'Attenuate the linear transient before limiting');
    else assert.equal(peak, 1);
  }
});
