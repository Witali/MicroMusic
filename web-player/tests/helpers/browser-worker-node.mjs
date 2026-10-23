// Run the real browser Worker in Node with only its messaging globals adapted.
import {parentPort} from 'node:worker_threads';
globalThis.self = globalThis;
self.postMessage = (data, transfer) => parentPort.postMessage(data, transfer);
const pending = [];
parentPort.on('message', data => {
  if (self.onmessage) self.onmessage({data}); else pending.push(data);
});
await import('../../worker.js');
for (const data of pending) self.onmessage({data});
