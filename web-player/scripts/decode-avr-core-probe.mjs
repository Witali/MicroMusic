// Decode a supplied raw 64-byte EEPROM dump; this script does not acquire it.
import {readFileSync} from 'node:fs';
import {parseArgs} from 'node:util';
import {createHash} from 'node:crypto';
import {decodeCoreProbe} from './lib/avr-core-probe-cases.mjs';
const {values}=parseArgs({options:{descriptor:{type:'string'},eeprom:{type:'string'}}});
if(!values.descriptor||!values.eeprom)throw Error('Required: --descriptor descriptor.json --eeprom dump.bin');
const descriptor=JSON.parse(readFileSync(values.descriptor)),bytes=readFileSync(values.eeprom);
const result=decodeCoreProbe(bytes,descriptor);
console.log(JSON.stringify({...result,source:'supplied EEPROM dump; acquisition provenance must be retained separately',
  dumpSha256:createHash('sha256').update(bytes).digest('hex'),flashSha256:descriptor.flashSha256},null,2));
if(!result.passed)process.exitCode=1;
