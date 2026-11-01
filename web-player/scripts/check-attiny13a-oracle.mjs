// Compare a project-local debugger observation; this does not verify its host.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync} from 'node:fs';
import {parseArgs} from 'node:util';
import {decodeAttiny13aOracle} from './lib/attiny13a-oracle-record.mjs';
const {values}=parseArgs({options:{descriptor:{type:'string'},capture:{type:'string'},output:{type:'string'}}});
assert.ok(values.descriptor&&values.capture,'Pass --descriptor and --capture JSON files');
const descriptor=JSON.parse(readFileSync(values.descriptor,'utf8'));
const capture=JSON.parse(readFileSync(values.capture,'utf8'));
assert.ok(['bytes','words'].includes(descriptor.breakpointAddressUnit),'Confirm the host breakpoint address unit first');
assert.equal(capture.schema,'micromusic-attiny13a-debug-observation-v1');
assert.equal(capture.captureKind,'unverified-debugger');assert.equal(capture.hostVerified,false);
assert.deepEqual(capture.buildId,descriptor.buildId);
assert.ok(Array.isArray(capture.record)&&capture.record.every(n=>Number.isInteger(n)&&n>=0&&n<=255));
const result=decodeAttiny13aOracle(Uint8Array.from(capture.record),descriptor);
const text=JSON.stringify(result,null,2)+'\n';
if(values.output)writeFileSync(values.output,text);else process.stdout.write(text);
if(!result.passed)process.exitCode=1;
