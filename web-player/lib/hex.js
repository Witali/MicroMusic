// Strict Intel HEX parser shared by the player, tests, and catalog checks.
export function parseHex(text, limit = 1024) {
  const memory = new Uint8Array(limit).fill(255);
  const present = new Uint8Array(limit);
  let end = 0, eof = false;
  for (const line of text.trim().split(/\s+/)) {
    if (eof) throw new Error('Data after HEX end record');
    if (!/^:(?:[\da-f]{2})+$/i.test(line)) throw new Error('Invalid HEX record');
    const bytes = Uint8Array.from(line.slice(1).match(/../g), x => parseInt(x, 16));
    const count = bytes[0], address = (bytes[1] << 8) | bytes[2], type = bytes[3];
    if (bytes.length !== count + 5 || bytes.reduce((a, b) => a + b, 0) % 256) throw new Error('HEX length or checksum mismatch');
    if (type === 1) {
      if (count || address) throw new Error('Invalid HEX end record');
      eof = true;
    } else if (type === 0) {
      if (address + count > limit) throw new Error('HEX exceeds device memory');
      for (let i = 0; i < count; i++) {
        if (present[address + i]) throw new Error('Overlapping HEX records');
        memory[address + i] = bytes[4 + i]; present[address + i] = 1;
      }
      end = Math.max(end, address + count);
    } else throw new Error('Unsupported HEX record type');
  }
  if (!eof || !end || present.subarray(0, end).some(x => !x)) throw new Error('Incomplete HEX image');
  return memory.slice(0, end);
}
