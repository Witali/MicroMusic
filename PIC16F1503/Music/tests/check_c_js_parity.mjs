/* Independently execute the real C port on the host and compare every duty
 * with the browser model. Does NOT validate XC8 timing or code size. */
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {mkdtempSync,rmSync} from 'node:fs';
import os from 'node:os';import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {SoundModel} from '../web/synth-model.mjs';
const root=fileURLToPath(new URL('..',import.meta.url));
const dir=mkdtempSync(path.join(os.tmpdir(),'pic16-c-parity-'));
try {
  const bin=path.join(dir,'host_ref');
  const gcc=spawnSync('gcc',['-std=c99','-O2','-I'+path.join(root,'tests'),'-I'+path.join(root,'firmware'),path.join(root,'tests/host_reference.c'),'-o',bin],{encoding:'utf8'});
  if(gcc.status!==0)throw Error('GCC compilation failed: '+gcc.stderr);
  const n=Number(process.argv[2]||120000);
  const c=spawnSync(bin,[String(n)],{maxBuffer:Math.max(1024*1024,n+1024)});
  if(c.status!==0)throw Error('Host firmware exited with code '+c.status+': '+c.stderr);
  assert.equal(c.stdout.length,n);
  const s=new SoundModel();let min=255,max=0,total=0;
  for(let i=0;i<n;i++){
    const picC=c.stdout[i],js=s.nextSample();
    if(picC!==js)throw Error('C vs JS mismatch at sample '+i+': C='+picC+', JS='+js);
    min=Math.min(min,js);max=Math.max(max,js);total+=js;
  }
  console.log(JSON.stringify({samples:n,result:'C and JavaScript duty values byte-for-byte identical',average:total/n,range:[min,max]},null,2));
}finally{rmSync(dir,{recursive:true,force:true});}
