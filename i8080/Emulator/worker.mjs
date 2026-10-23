import { CPU8080, AudioBus } from './core8080.mjs';

// Each run gets its own worker; terminate() also cancels queued chunks.
let paused = false, played = 0;
self.onmessage = event => {
  if (event.data.kind === 'pause' || event.data.kind === 'resume') { paused = event.data.kind === 'pause'; return; }
  if (event.data.kind === 'played') { played = event.data.seconds; return; }
  let cpu;
  try {
    const o = event.data;
    const audio = new AudioBus(o.hz, o.rate, o.output, o.seconds, 1);
    cpu = new CPU8080(new Uint8Array(o.rom), { memoryMode: o.memoryMode, mode: o.output, inputByte: o.inputByte, audio });
    const maxT = o.seconds * o.hz, maxInstructions = 150000000;
    let sentSamples = 0;
    function sendAudio(samples, end) {
      if (!o.realtime || end <= sentSamples) return;
      const chunk = samples.slice(sentSamples, end); sentSamples = end;
      self.postMessage({ kind: 'audio', audio: chunk.buffer }, [chunk.buffer]);
    }
    function runChunk() {
      try {
        if (paused || (o.realtime && cpu.t / o.hz - played > 2)) { setTimeout(runChunk, 20); return; }
        let steps = 0;
        while (!cpu.halted && cpu.t < maxT && cpu.count < maxInstructions && steps++ < 120000) cpu.step();
        sendAudio(audio.samples, audio.i);
        if (!cpu.halted && cpu.t < maxT && cpu.count < maxInstructions) {
          self.postMessage({ kind: 'progress', steps: cpu.count, seconds: cpu.t / o.hz, t: cpu.t,
            pc: cpu.pc, sp: cpu.sp, flags: cpu.packFlags(), registers: Array.from(cpu.r),
            inte: cpu.inte, memWrites: cpu.memWrites, ignoredWrites: cpu.ignoredWrites,
            ioWrites: cpu.ioWrites, edges: audio.edges });
          setTimeout(runChunk, 0);
          return;
        }
        const samples = audio.finish(cpu.t);
        sendAudio(samples, samples.length);
        self.postMessage({ kind: 'done', audio: samples.buffer, steps: cpu.count, t: cpu.t,
          halted: cpu.halted, pc: cpu.pc, sp: cpu.sp, flags: cpu.packFlags(), registers: Array.from(cpu.r),
          memWrites: cpu.memWrites, ignoredWrites: cpu.ignoredWrites, ioWrites: cpu.ioWrites,
          inte: cpu.inte, edges: audio.edges, rate: o.rate,
          stopReason: cpu.halted ? 'HLT' : cpu.t >= maxT ? 'time_limit' : 'instruction_limit' }, [samples.buffer]);
      } catch (error) {
        self.postMessage({ kind: 'error', message: error.message, pc: cpu.pc, t: cpu.t, steps: cpu.count });
      }
    }
    runChunk();
  } catch (error) { self.postMessage({ kind: 'error', message: error.message }); }
};
