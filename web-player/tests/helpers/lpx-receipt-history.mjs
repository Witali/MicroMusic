import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';

const root=new URL('../../../',import.meta.url);
const folder='Codecs/LPX/01_ACTIVE_Q0_CODEC/examples/ATTINY88_V5_PLAYER/';
const read=path=>readFileSync(new URL(path,root));
const sha=data=>createHash('sha256').update(data).digest('hex');

// These receipts measured the earlier two-profile decoder. The new admission
// checks their exact content/source digests against Git e32e0c66, then replays
// those ELFs. Current three-profile source binding is checked separately.
export function assertHistoricalReceipt(name,receipt){
  const current=JSON.parse(read(folder+'v9-sparse80-measurements.json'));
  assert.equal(current.baseline_revision,'e32e0c66');
  assert.equal(sha(read(folder+name).toString('utf8').replaceAll('\r\n','\n')),
    current.historical_receipt_sha256[name],name);
  for(const [path,digest] of Object.entries(receipt.source_sha256))
    assert.equal(digest,current.baseline_source_sha256[path],path);
}
