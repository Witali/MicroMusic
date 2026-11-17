// Full signed-domain and coefficient-domain proof of the actual extracted source.
import {readFileSync,writeFileSync,existsSync} from 'node:fs';
import {resolve,dirname,join} from 'node:path';
import {pathToFileURL,fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import assert from 'node:assert/strict';

let repo=dirname(fileURLToPath(import.meta.url));
while(!existsSync(join(repo,'web-player/lib/avr-transpiled.js'))){
    const parent=dirname(repo);assert.notEqual(parent,repo,'Repository root');repo=parent;
}
const {AVRCore}=await import(pathToFileURL(join(repo,'web-player/lib/avr-transpiled.js')));
const folder=resolve(process.argv[2]);
const sha=p=>createHash('sha256').update(readFileSync(p)).digest('hex');
const build=JSON.parse(readFileSync(join(folder,'build.json'),'utf8'));
const oracle=readFileSync(join(folder,'expected.bin'));
const coefficients=[0,1,63,64,65,7800,8192,13094,13926,11468,11469,16383,16384];
const boundary=[-32768,-16384,-1,0,1,16384,32767];
const full=coefficients.length*65536;
assert.equal(oracle.length,2*(full+16385*boundary.length));
assert.equal(sha(join(folder,'expected.bin')),build.oracle_sha256);
assert.ok(readFileSync(join(folder,'c.bin')).equals(readFileSync(join(folder,'generic.bin'))),
    'Explicit generic architecture retains the C image');
for(const [name,hash] of Object.entries(build.extracted_source_lf_sha256)){
    const text=readFileSync(join(folder,'source',name),'utf8').replaceAll('\r\n','\n');
    assert.equal(createHash('sha256').update(text).digest('hex'),hash,`Frozen ${name}`);
}
const rows=[];
for(const backend of ['asm','c']){
    const image=readFileSync(join(folder,backend+'.bin'));
    assert.equal(sha(join(folder,backend+'.bin')),build.backends[backend].image_sha256);
    const symbols=readFileSync(join(folder,backend+'.nm'),'utf8').split(/\r?\n/);
    const addresses=new Map();
    const sym=name=>{
        if(!addresses.has(name)){
            const line=symbols.find(line=>line.trim().endsWith(' '+name));assert.ok(line,name);
            addresses.set(name,parseInt(line.trim().split(/\s+/)[0],16)&65535);
        }
        return addresses.get(name);
    };
    const cpu=new AVRCore(image,null,{target:'attiny88',cpuHz:16000000,
        fastIdle:false,fastBlocks:false,optimizeFlags:false,cacheTranslation:false});
    while(!cpu.data[sym('filter_ready')]){cpu.step();assert.ok(cpu.cyc<20000);}
    assert.equal(cpu.data[sym('filter_backend')],backend==='asm'?1:0,'Actual arithmetic backend');
    const preserved=[2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,28,29];
    let cases=0,seenIrq=false;
    function call(name,state,coefficient){
        cpu.r[24]=state;cpu.r[25]=state>>8;cpu.r[22]=coefficient;cpu.r[23]=coefficient>>8;
        preserved.forEach(r=>cpu.r[r]=(r*7+cases)&255);
        // Preparation is C++ and follows the normal zero-register ABI.
        const zero=backend==='asm'&&name==='filter_product'&&cases%8===0?71:0;
        cpu.r[1]=zero;
        const sp=cpu.sp,start=cpu.cyc;cpu.pushPC(0);cpu.pc=sym(name)/2;
        do{cpu.step();assert.ok(cpu.cyc-start<4000,'Bounded arithmetic call');}while(cpu.pc!==0);
        assert.equal(cpu.sp,sp,'Stack balance');assert.equal(cpu.r[1],zero,'Zero register retained');
        preserved.forEach(r=>assert.equal(cpu.r[r],(r*7+cases)&255,`Callee-saved r${r}`));
        seenIrq ||= Boolean(cpu.data[sym('filter_irqs')]|cpu.data[sym('filter_irqs')+1]<<8);
        return (cpu.r[24]|cpu.r[25]<<8)<<16>>16;
    }
    if(backend==='asm'){
        let at=0;
        for(const coefficient of coefficients){
            const tag=call('filter_prepare',coefficient,0);
            for(let state=-32768;state<=32767;state++){
                assert.equal(call('filter_product',state,tag),oracle.readInt16LE(at),
                    `ASM signed domain coefficient${coefficient} state${state}`);
                at+=2;cases++;
            }
        }
    }
    let at=full*2;
    for(let coefficient=0;coefficient<=16384;coefficient++){
        const tag=call('filter_prepare',coefficient,0);
        for(const state of boundary){
            assert.equal(call('filter_product',state,tag),oracle.readInt16LE(at),
                `${backend} coefficient domain coefficient${coefficient} state${state}`);
            at+=2;cases++;
        }
    }
    assert.ok(seenIrq,'Interrupts occurred during arithmetic');
    const result={backend,cases,signed_domain_cases:backend==='asm'?full:0,
        coefficient_domain_cases:16385*boundary.length,valid_coefficients:16385,
        interrupts_observed:true,registers_and_stack_preserved:true,passed:true};
    rows.push(result);console.log(JSON.stringify(result));
}
const result={schema:'lpx-avr25-prepared-filter-exactness-v1',target:'attiny88',cpu_hz:16000000,
    source_lf_sha256:build.source_lf_sha256,extracted_source_lf_sha256:build.extracted_source_lf_sha256,
    portable_c_cases:full+16385*boundary.length,portable_c_explicit_floor_oracle:true,
    explicit_c_on_avr:true,explicit_generic_image_equals_c:true,rows,
    physical_board_measured:false,audio_realtime_admission_test:false,
    build_sha256:sha(join(folder,'build.json')),observer_lf_sha256:createHash('sha256').update(
        readFileSync(fileURLToPath(import.meta.url),'utf8').replaceAll('\r\n','\n')).digest('hex')};
writeFileSync(join(folder,'verification.json'),JSON.stringify(result,null,2)+'\n');
