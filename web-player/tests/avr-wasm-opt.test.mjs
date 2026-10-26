import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdtempSync,rmSync} from 'node:fs';
import {join,dirname,resolve} from 'node:path';
import {tmpdir} from 'node:os';
import {spawnSync} from 'node:child_process';
import {ATtiny13A,runtimeModule} from '../lib/attiny13a.js';
import {runtimeABI,transpileAVR} from '../lib/avr-transpiler.js';
import {createPackage} from '../lib/attiny13a-package.js';
import {findWasmOpt,optimizeAVRWasm} from '../scripts/lib/optimize-avr-wasm.mjs';
import {avr,IO,sequential,flash} from './fixtures/attiny13a-system-firmware.mjs';
import {put} from './helpers/avr-test-state.mjs';

const wasmOpt=findWasmOpt(),skip=wasmOpt?false:'Optional Binaryen SDK is unavailable';
const runtime=readFileSync(new URL('../wasm/attiny13a.wasm',import.meta.url));
const {instructions}=JSON.parse(readFileSync(new URL('../reports/attiny13a-instructions.json',import.meta.url)));
const image=new Uint8Array(1024).fill(255);
for(const [n,entry]of instructions.entries()){
  let word=parseInt(entry.opcodePattern.replaceAll(' ','').replace(/[^01]/g,'0'),2);
  if(/^(IN|OUT)$/.test(entry.form))word|=(IO.PORTB&15)|((IO.PORTB&48)<<5);
  if(/^(SBI|CBI|SBIC|SBIS)$/.test(entry.form))word|=IO.PORTB<<3;
  put(image,n*3,word);put(image,n*3+1,0);
}
const abi=resumable=>runtimeABI(new WebAssembly.Instance(runtimeModule).exports,{resumable});
const snapshot=c=>({state:c.state(),data:c.data.slice(),eeprom:c.eeprom.slice(),rom:c.rom.slice(),diagnostics:Array.from(c._state)});
function initialize(c,n,entry){
  c._call('avr_reset',0,0);c.pc=n*3;c.sreg=0x73;
  if(entry.form==='RET'||entry.form==='RETI')c.pushPC(1);
  if(entry.form==='POP')c.push(0xa5);
  if(/^(LD|LDD|ST|STD) /.test(entry.form))for(const pointer of [26,28,30])c.r[pointer]=97;
}
test('optimizer rejects unsupported levels without invoking a tool',()=>{
  assert.throws(()=>optimizeAVRWasm({}, {level:'fast'}),/level must be/);
});
for(const level of ['O3','Oz'])for(const resumable of [false,true]){
  test(`${level}: all123 forms preserve ${resumable?'unequal CLKI half phases and WAIT':'instruction effects and cycle counts'}`,{skip},async()=>{
    const generated=transpileAVR(image,abi(resumable),{resumable}),optimized=optimizeAVRWasm(generated,{level,wasmOpt});
    assert.ok(optimized.optimization.outputBytes<optimized.optimization.inputBytes);
    const options={resumable,fastIdle:false,spmCommandCycles:1,...(resumable?{
      fuseLow:0x70,clkiProfile:{phasePolicy:'digital-noninverting-zero-seed-v1',initialLevel:1}}:{})};
    const a=new ATtiny13A(image,null,{...options,precompiled:optimized}),b=new ATtiny13A(image,null,{...options,precompiled:generated});
    // Exercise the unchanged public package validator and loader as well.
    const {fastIdle,...configuration}=options;
    const pkg=await createPackage({flash:image,runtime,translated:optimized.bytes,configuration});
    const loaded=await ATtiny13A.fromPackage(pkg);assert.deepEqual(loaded.transpiledBytes,optimized.bytes);
    for(const [n,entry]of instructions.entries()){
      for(const c of [a,b])initialize(c,n,entry);
      if(!resumable){a.step();b.step();assert.deepEqual(snapshot(a),snapshot(b),entry.form);continue;}
      let at=0n,level=1;
      const edges=Array.from({length:20},()=>{at+=level?70000n:30000n;level^=1;return{timePs:at,level};});
      for(const c of [a,b])assert.equal(c.injectClkiPs({edges,knownUntilPs:at}),true);
      let retired=0;
      for(const edge of edges){
        for(const deadline of [edge.timePs-1n,edge.timePs]){
          const actual=a.runUntilPs(deadline),expected=b.runUntilPs(deadline);
          assert.equal(actual,expected,entry.form+' retirement');retired+=actual;
          assert.deepEqual(snapshot(a),snapshot(b),entry.form+' at '+deadline);
          assert.deepEqual(a.drainPinsPs(),b.drainPinsPs(),entry.form+' pins');
        }
        if(retired)break;
      }
      assert.equal(retired,1,entry.form+' must retire exactly once');
    }
  });
}
test('optimized SPM under a held CLKI invalidates Flash before the next fetch',{skip},()=>{
  const image=flash({instructions:[[0x95e8],avr.rjmp(1,128)]},{at:128,instructions:[avr.ldi(20,17),avr.rjmp(129,129)]});
  const options={resumable:true,fuseLow:0x70,fuseHigh:0xef,clkiProfile:{phasePolicy:'digital-noninverting-zero-seed-v1',initialLevel:1},
    nvmClockProfile:1,nvmCalibrationReferenceHz:9600000,spmCommandCycles:1};
  const raw=transpileAVR(image,abi(true),options),optimized=optimizeAVRWasm(raw,{level:'Oz',wasmOpt});
  const cores=[optimized,raw].map(precompiled=>new ATtiny13A(image,null,{...options,precompiled}));
  for(const c of cores){
    c.r[30]=0;c.r[31]=1;c.writeIO(IO.SPMCSR,3);const module=c._translatedModule;
    assert.equal(c.injectClkiPs({edges:[],knownUntilPs:5000000000n}),true);assert.equal(c.runUntilPs(5000000000n),1);
    assert.notEqual(c._translatedModule,module);assert.equal(c.transpilation.mapping[128].word,0xffff);
    assert.equal(c._exports.avr_device_generation(),1n);assert.equal(c.state().cpuPhase.active,0);
    assert.equal(c.cyc,0);assert.equal(c.pc,1);
  }
  assert.deepEqual(snapshot(cores[0]),snapshot(cores[1]));
});
test('CLI emits optimized legacy/device WASM and an executable full-device package',{skip},async()=>{
  const directory=mkdtempSync(join(tmpdir(),'micromusic-opt-cli-'));
  try{
    const input=join(directory,'input.bin'),output=join(directory,'output.wasm'),packageFile=join(directory,'package.json');
    writeFileSync(input,sequential([avr.ldi(16,42)]));
    const run=(script,args)=>{
      const r=spawnSync(process.execPath,[new URL('../scripts/'+script,import.meta.url).pathname.replace(/^\/([A-Z]:)/,'$1'),...args],{encoding:'utf8',windowsHide:true});
      assert.equal(r.status,0,r.stderr);return r.stdout;
    };
    for(const device of [false,true]){
      run('transpile-avr.mjs',[input,output,...device?['--device']:[],'--optimize','Oz','--wasm-opt',wasmOpt]);
      const report=JSON.parse(readFileSync(output+'.json','utf8'));
      assert.equal(report.optimization.outputBytes,readFileSync(output).length);
      assert.ok(report.optimization.flags.includes('--skip-pass=remove-unused-module-elements'));
      assert.equal(WebAssembly.validate(readFileSync(output)),true);
    }
    const result=JSON.parse(run('package-attiny13a.mjs',['pack',input,packageFile,'--optimize','Oz','--wasm-opt',wasmOpt]));
    assert.ok(result.optimization.outputBytes<result.optimization.inputBytes);
    const c=await ATtiny13A.fromPackage(JSON.parse(readFileSync(packageFile,'utf8')));c.step();assert.equal(c.r[16],42);
    run('package-attiny13a.mjs',['verify',packageFile]);
  }finally{
    assert.equal(dirname(directory),resolve(tmpdir()));rmSync(directory,{recursive:true,force:true});
  }
});
