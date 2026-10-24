/** Native LPC2 Voice v2 browser functions, executed unchanged without a DOM. */
import fs from 'node:fs/promises';
import path from 'node:path';
import vm from 'node:vm';
import crypto from 'node:crypto';
import { fileURLToPath, pathToFileURL } from 'node:url';

export const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
export const HTML = path.join(ROOT, 'ATmega328/Sound/reference/lpx3/lpc2_v2_reference.html');
export const PURE = path.join(ROOT, 'ATmega328/Sound/reference/lpx3/lpx3_decoder.js');
const sha = value => crypto.createHash('sha256').update(value).digest('hex');
const normalized = value => value.replace(/\r\n/g, '\n');
const exactArrayBuffer = bytes => bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset+bytes.byteLength);

function region(source, startMarker, endMarker) {
  const start=source.indexOf(startMarker), end=source.indexOf(endMarker, start+startMarker.length);
  if (start<0 || end<=start) throw Error(`Missing unique codec region: ${startMarker}`);
  if (source.indexOf(startMarker,start+startMarker.length)>=0) throw Error(`Ambiguous codec marker: ${startMarker}`);
  const text=source.slice(start,end);
  return {text,startLine:source.slice(0,start).split('\n').length,endLine:source.slice(0,end).split('\n').length-1,
    sha256NormalizedLf:sha(text)};
}

export async function loadReference() {
  const htmlBytes=await fs.readFile(HTML), pureBytes=await fs.readFile(PURE);
  const html=normalized(htmlBytes.toString('utf8')), pure=normalized(pureBytes.toString('utf8'));
  const core=region(html,'const LPC_CHIRP=','function splitForBlocks(');
  const clamp=html.match(/^const clamp=.*$/m)?.[0];
  if (!clamp) throw Error('Missing original clamp/tick declaration');
  const context=vm.createContext({setTimeout,progress:()=>{},status:()=>{}});
  vm.runInContext(`"use strict";\n${clamp}\n${core.text}\nglobalThis.api={encodeLPC2,packLPC2,unpackLPC2,synthLPC2,decodeLpc2FrameLsf,lsfToLpc,stabilizeLsf,defaultLsf,qLpcGain,qLpc2Pitch,setPitchRange:(lo,hi)=>{LPC2_PITCH_MIN=lo;LPC2_PITCH_MAX=hi}};`,context,{filename:HTML,timeout:10000});
  const audit={current:null},nativeMath=vm.runInContext('Math',context),nativeMin=nativeMath.min;
  // Observe the original clamp's Math.min(limit,x) without changing its value
  // or any codec function source. Enabled only during audio synthesis.
  nativeMath.min=(...args)=>{
    if (audit.current&&args.length===2&&(args[0]===8||args[0]===6)) {
      const limit=args[0],value=args[1],key=String(limit),record=audit.current[key]??={calls:0,outside:0,positive:0,negative:0,maxUnclippedAbs:0};
      record.calls++;record.maxUnclippedAbs=Math.max(record.maxUnclippedAbs,Math.abs(value));
      if (value>limit||value< -limit) {record.outside++;if(value>limit)record.positive++;else record.negative++;}
    }
    return Reflect.apply(nativeMin,nativeMath,args);
  };
  const independent=vm.createContext({});
  vm.runInContext(`${pure}\nglobalThis.api={unpackLPC2,decodeLpc2FrameLsf,lsfToLpc,stabilizeLsf,defaultLsf,decodeLPX3};`,independent,{filename:PURE,timeout:10000});
  return {api:context.api,pure:independent.api,audit,provenance:{
    referencePath:path.relative(ROOT,HTML).replaceAll('\\','/'),htmlSha256:sha(htmlBytes),
    htmlSha256NormalizedLf:sha(html),core:{startLine:core.startLine,endLine:core.endLine,sha256NormalizedLf:core.sha256NormalizedLf},
    clampTickSha256NormalizedLf:sha(clamp),pureDecoderPath:path.relative(ROOT,PURE).replaceAll('\\','/'),
    pureDecoderSha256NormalizedLf:sha(pure),hostPolicy:'No DOM/browser/audio host; no-op progress/status and native setTimeout; same-value Math.min observer counts audio clamps only; codec function source is unchanged'}};
}

export function outputStats(pcm) {
  let min=Infinity,max=-Infinity,sum=0,outsideUnit=0,repeated=0,longest=0,run=0,plateaus=0,zeros=0,atEight=0;
  for (let i=0;i<pcm.length;i++) {
    const value=pcm[i];min=Math.min(min,value);max=Math.max(max,value);sum+=value;
    outsideUnit+=Number(Math.abs(value)>1);zeros+=Number(value===0);atEight+=Number(Math.abs(value)===8);
    if(i&&Object.is(value,pcm[i-1])) {repeated++;run++;} else {if(run>=4)plateaus++;longest=Math.max(longest,run);run=1;}
  }
  if(run>=4)plateaus++;longest=Math.max(longest,run);
  return {minimum:min,maximum:max,mean:sum/pcm.length,samplesOutsideUnitRange:outsideUnit,
    samplesAtEight:atEight,zeroSamples:zeros,repeatedAdjacentSamples:repeated,longestExactPlateauSamples:longest,plateauRunsAtLeastFourSamples:plateaus};
}

export function validateContainer(bytes) {
  if (!(bytes instanceof Uint8Array) || bytes.byteLength<36) throw Error('Truncated LPC2 header');
  const view=new DataView(bytes.buffer,bytes.byteOffset,bytes.byteLength);
  const magic=String.fromCharCode(...bytes.subarray(0,4)), version=view.getUint8(4);
  const sr=view.getUint16(6,true),hop=view.getUint16(8,true),window=view.getUint16(10,true);
  const frames=view.getUint32(12,true),samples=view.getUint32(16,true),bits=view.getUint32(20,true);
  const pre=view.getFloat32(24,true),voicing=view.getFloat32(28,true);
  if (magic!=='LPC2'||![1,2].includes(version)||view.getUint8(5)!==10||sr<4000||sr>96000||hop<16||window<hop||
      !samples||samples>sr*3600||frames!==Math.ceil(samples/hop)||!bits||bytes.length!==36+Math.ceil(bits/8)||
      !Number.isFinite(pre)||pre<0||pre>.99||!Number.isFinite(voicing)||voicing<0||voicing>1) throw Error('Invalid or noncanonical LPC2 header/length');
  if (version===2 && (view.getUint16(32,true)<20||view.getUint16(34,true)>2500||view.getUint16(34,true)<=view.getUint16(32,true))) throw Error('Invalid LPC2 pitch range');
  if (bits%8 && (bytes.at(-1) >>> (bits%8))) throw Error('Nonzero LPC2 padding bits');
  return {version,sr,hop,window,frames,samples,bits};
}

export function unpackStrict(engine, bytes) {
  const header=validateContainer(bytes), decoded=engine.api.unpackLPC2(exactArrayBuffer(bytes));
  let used=0;
  for (const frame of decoded.frames) {
    used+=5;
    if (frame.energy) used+=3+([1,2].includes(frame.mode)?6:0)+(frame.repeat?0:([1,2].includes(frame.mode)?39:18));
  }
  if (used!==header.bits) throw Error('LPC2 payload bit count does not match decoded frames');
  const repacked=new Uint8Array(engine.api.packLPC2(decoded.meta,decoded.frames).buffer);
  // The native packer writes v2. Retain v1 support in the original decoder;
  // canonical equality is asserted for the v2 streams produced by this tool.
  if (header.version===2 && !Buffer.from(bytes).equals(Buffer.from(repacked))) throw Error('LPC2 native repacking differs');
  return decoded;
}

export function coefficientTrajectory(api, meta, frames) {
  const decoded=frames.map(frame=>api.decodeLpc2FrameLsf(frame));
  const coefficients=new Float64Array(meta.samples*10);
  let previous=decoded[0]||api.defaultLsf(10);
  // Exact LPX3 v1 descriptor convention: eight linear-LSF subframes, no
  // LPC2 synthesizer transient fast-attack. Only the embedded base is used.
  for (let fi=0;fi<frames.length;fi++) {
    const current=decoded[fi];
    for (let sub=0;sub<8;sub++) {
      const start=fi*meta.H+Math.floor(sub*meta.H/8),end=Math.min(meta.samples,fi*meta.H+Math.floor((sub+1)*meta.H/8));
      if (start>=meta.samples) break;
      const t=(sub+.5)/8;
      const co=api.lsfToLpc(api.stabilizeLsf(current.map((v,i)=>previous[i]+(v-previous[i])*t),10));
      for (let n=start;n<end;n++) for (let k=0;k<10;k++) coefficients[n*10+k]=co[k+1];
    }
    previous=current;
  }
  return {coefficients,frameLsf:decoded.map(value=>Array.from(value)),
    frameCoefficients:decoded.map(value=>Array.from(api.lsfToLpc(value)).slice(1))};
}

export async function decodeReference(engine, bytes, posts=[0,.1,.35],{audit=true}={}) {
  const checked=unpackStrict(engine,bytes), trajectory=coefficientTrajectory(engine.api,checked.meta,checked.frames);
  const pure=engine.pure.unpackLPC2(exactArrayBuffer(bytes));
  const independent=coefficientTrajectory(engine.pure,pure.meta,pure.frames);
  const same=(a,b)=>a.length===b.length&&a.every((value,i)=>Object.is(value,b[i]));
  if (JSON.stringify(checked.meta)!==JSON.stringify(pure.meta)||JSON.stringify(checked.frames)!==JSON.stringify(pure.frames)||
      !same(trajectory.coefficients,independent.coefficients)) throw Error('HTML/pure LPX3 descriptor disagreement');
  const outputs={},clippingAudit={};
  for (const post of posts) {
    if (!Number.isFinite(post)||post<0||post>.7) throw Error('Postfilter must be in 0..0.7');
    const counts={};let pcm;
    try {engine.audit.current=audit?counts:null;pcm=await engine.api.synthLPC2(checked.meta,checked.frames,post);}
    finally {engine.audit.current=null;}
    if (pcm.length!==checked.meta.samples||!Array.from(pcm).every(Number.isFinite)) throw Error('Invalid native LPC2 synthesis');
    outputs[String(post)]=pcm;
    clippingAudit[String(post)]={instrumented:audit,protectiveClamps:counts,rawOutput:outputStats(pcm),
      policy:'Original clamp arguments observed with identical return values; output is not normalized or saturated by the adapter'};
  }
  return {...checked,...trajectory,outputs,clippingAudit,independentAgreement:{header:true,frames:true,lsfAndPredictorTrajectoryExact:true},
    frameGain:checked.frames.map(frame=>engine.api.qLpcGain(frame.energy)),
    frameF0:checked.frames.map(frame=>[1,2].includes(frame.mode)?checked.meta.sr/engine.api.qLpc2Pitch(frame.pitch,checked.meta.sr,checked.meta.pitchMin,checked.meta.pitchMax):0)};
}

export async function encodeReference(input, engine=null) {
  engine??=await loadReference();
  const sr=Number(input.sampleRate??7500),samples=input.samples;
  if (!Number.isInteger(sr)||sr<4000||sr>65535||!Array.isArray(samples)||!samples.length||samples.length>sr*3600||
      !samples.every(value=>typeof value==='number'&&Number.isFinite(value)&&Math.abs(value)<=16)) throw Error('Expected finite mono samples, 4000..65535Hz (uint16 header), and bounded WAV headroom');
  const config={frameMs:20,windowMs:32,pre:.85,voicing:.38,pitchSmooth:.65,repeat:.05,pitchMin:65,pitchMax:850,postfilter:.35,...input.config};
  const allowed=new Set(['frameMs','windowMs','pre','voicing','pitchSmooth','repeat','pitchMin','pitchMax','postfilter']);
  if (Object.keys(input.config??{}).some(key=>!allowed.has(key))||Object.values(config).some(value=>!Number.isFinite(value))||
      config.frameMs<5||config.frameMs>100||config.windowMs<config.frameMs||config.windowMs>100||config.pre<0||config.pre>.99||
      config.voicing<0||config.voicing>1||config.pitchSmooth<0||config.pitchSmooth>1||config.repeat<0||config.repeat>1||
      !Number.isInteger(config.pitchMin)||!Number.isInteger(config.pitchMax)||config.pitchMin<20||config.pitchMax>2500||config.pitchMax<=config.pitchMin||
      config.postfilter<0||config.postfilter>.7) throw Error('Invalid/unsupported LPC2 configuration; external pitch guides are not accepted');
  engine.api.setPitchRange(config.pitchMin,config.pitchMax);
  // The browser's resample/normalize-off path also supplies Float32 samples.
  // There is no resampling, gain normalization, DC removal, or cropping here.
  const browserInput=Float32Array.from(samples);
  const analyzed=await engine.api.encodeLPC2(browserInput,sr,config);
  const bytes=Buffer.from(new Uint8Array(engine.api.packLPC2(analyzed.meta,analyzed.frames,analyzed.analysis).buffer));
  return {bytes,config,analysis:analyzed.analysis,engine,
    decoded:await decodeReference(engine,bytes,[...new Set([0,.1,.35,config.postfilter])])};
}

function floatBytes(values,bits) {
  const bytes=Buffer.alloc(values.length*bits/8),view=new DataView(bytes.buffer,bytes.byteOffset,bytes.byteLength);
  for (let i=0;i<values.length;i++) bits===32?view.setFloat32(i*4,values[i],true):view.setFloat64(i*8,values[i],true);
  return bytes;
}

export async function main(argv=process.argv.slice(2)) {
  const args={};
  for (let i=0;i<argv.length;i+=2) {
    if (!['--input','--base','--output'].includes(argv[i])||argv[i+1]===undefined) throw Error('Usage: --input samples.json OR --base base.lp2 --output directory');
    args[argv[i].slice(2)]=argv[i+1];
  }
  if (!args.output||Boolean(args.input)===Boolean(args.base)) throw Error('Choose exactly one input JSON or parameter-only base LPC2');
  const engine=await loadReference();
  let bytes,config=null,analysis=null,decoded,inputSha;
  if (args.input) {
    const raw=await fs.readFile(args.input);inputSha=sha(raw);
    const result=await encodeReference(JSON.parse(raw.toString('utf8')),engine);
    ({bytes,config,analysis,decoded}=result);
  } else {
    bytes=await fs.readFile(args.base);inputSha=sha(bytes);
    decoded=await decodeReference(engine,bytes);
  }
  await fs.mkdir(args.output,{recursive:true});
  await fs.writeFile(path.join(args.output,'base.lp2'),bytes);
  await fs.writeFile(path.join(args.output,'coefficients.f64le'),floatBytes(decoded.coefficients,64));
  const outputHashes={};
  for (const [post,pcm] of Object.entries(decoded.outputs)) {
    const raw=floatBytes(pcm,32),name=`decoded-post-${post}.f32`;
    await fs.writeFile(path.join(args.output,name),raw);outputHashes[name]=sha(raw);
  }
  const chosen=String(config?.postfilter??.35),raw=floatBytes(decoded.outputs[chosen],32);
  await fs.writeFile(path.join(args.output,'decoded.f32'),raw);
  const metadata={schema:'native-lpc2-reference-v1',mode:args.input?'encode':'parameter-only-decode',
    inputSha256:inputSha,baseSha256:sha(bytes),baseBytes:bytes.length,config,analysis,
    meta:decoded.meta,frames:decoded.frames,stats:decoded.stats,frameLsf:decoded.frameLsf,
    frameCoefficients:decoded.frameCoefficients,frameGain:decoded.frameGain,frameF0:decoded.frameF0,
    coefficients:{file:'coefficients.f64le',dtype:'float64-little-endian',shape:[decoded.meta.samples,10],
      convention:'LPX3 v1 eight-subframe linear-LSF interpolation, a[1..10], row-major; derived only from base.lp2'},
    decoderPosts:Object.keys(decoded.outputs).map(Number),selectedPostfilter:Number(chosen),outputHashes,
    inputProcessing:'Float32 precision, matching browser normalize-off path; no gain/DC/crop/resampling',
    outputProcessing:'Raw native synthLPC2; no browser brightness/highpass/limiter or original-signal correction',
    sideInformation:'No original PCM, external pitch guide, residual, or hidden encoder state is required to decode base.lp2',
    independentAgreement:decoded.independentAgreement,provenance:engine.provenance,
    clippingAudit:decoded.clippingAudit,
    adapterSha256NormalizedLf:sha(normalized(await fs.readFile(fileURLToPath(import.meta.url),'utf8')))};
  await fs.writeFile(path.join(args.output,'meta.json'),JSON.stringify(metadata,null,2)+'\n');
  process.stdout.write(JSON.stringify({baseBytes:bytes.length,samples:decoded.meta.samples,sampleRate:decoded.meta.sr,mode:metadata.mode,independentAgreement:metadata.independentAgreement})+'\n');
}

if (process.argv[1]&&import.meta.url===pathToFileURL(path.resolve(process.argv[1])).href) {
  main().catch(error=>{process.stderr.write(`${error.stack??error}\n`);process.exitCode=1;});
}
