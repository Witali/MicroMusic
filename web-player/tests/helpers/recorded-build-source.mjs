import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';

const root=new URL('../../../',import.meta.url);
const textSha=bytes=>createHash('sha256').update(bytes.toString('utf8').replaceAll('\r\n','\n')).digest('hex');

export function readRecordedBuildFile(revision,path){
  return execFileSync('git',['show',`${revision}:${path}`],{cwd:fileURLToPath(root)});
}

export function assertRecordedBuildSource(revision,path,digest){
  if(textSha(readFileSync(new URL(path,root)))===digest)return;
  assert.equal(textSha(readRecordedBuildFile(revision,path)),digest,`${revision}:${path}`);
}
