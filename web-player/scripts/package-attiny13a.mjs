import {readFile,writeFile,mkdir,stat} from 'node:fs/promises';
import {resolve,extname} from 'node:path';
import {parseArgs} from 'node:util';
import {createHash} from 'node:crypto';
import {createPackage,decodePackage,PACKAGE_FORMAT,PACKAGE_VERSION,PACKAGE_LIMITS} from '../lib/attiny13a-package.js';
import {runtimeABI,transpileAVR} from '../lib/avr-transpiler.js';
import {parseHex} from '../lib/hex.js';

const usage=`Usage:
  node web-player/scripts/package-attiny13a.mjs pack input.hex|bin output.json [--eeprom image.bin] [--configuration config.json] [--no-flag-dce]
  node web-player/scripts/package-attiny13a.mjs pack input.hex|bin output.json --translated firmware.wasm --runtime runtime.wasm [--eeprom image.bin] [--configuration config.json]
  node web-player/scripts/package-attiny13a.mjs verify package.json
  node web-player/scripts/package-attiny13a.mjs unpack package.json new-directory

pack uses the bundled full-device runtime, or packages an existing translation/runtime pair.
verify/unpack validate every component before loading bytes; they do not execute WASM.
Output paths must be new. SHA-256 verifies integrity, not authenticity.`;
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
async function read(path,limit){
  if((await stat(path)).size>limit)throw new Error('Input exceeds size limit: '+path);
  const bytes=await readFile(path);if(bytes.length>limit)throw new Error('Input exceeds size limit: '+path);return bytes;
}
const summary=decoded=>({format:PACKAGE_FORMAT,version:decoded.version??PACKAGE_VERSION,device:'ATtiny13A',abi:decoded.abi.id,
  flashBytes:decoded.flash.length,eepromBytes:decoded.eeprom.length,translatedBytes:decoded.translated.length,runtimeBytes:decoded.runtime.length,
  integrity:decoded.integrity,configuration:decoded.configuration});
async function main(){
  const {values,positionals}=parseArgs({allowPositionals:true,options:{help:{type:'boolean'},
    eeprom:{type:'string'},configuration:{type:'string'},translated:{type:'string'},runtime:{type:'string'},'no-flag-dce':{type:'boolean'}}});
  if(values.help){console.log(usage);return;}
  const [command,...args]=positionals;
  if(!['pack','verify','unpack'].includes(command)||args.length!==(command==='verify'?1:2))throw new Error(usage);
  if(command!=='pack'&&Object.keys(values).length)throw new Error('Options are only supported by pack');
  if(command==='pack'){
    const [input,output]=args.map(p=>resolve(p));
    if(input===output)throw new Error('Input and output paths must differ');
    if(!!values.translated!==!!values.runtime)throw new Error('--translated and --runtime must be used together');
    if(values.translated&&values['no-flag-dce'])throw new Error('--no-flag-dce only applies to newly generated translations');
    const source=await read(input,65536),flash=extname(input).toLowerCase()==='.hex'?parseHex(source.toString('utf8')):new Uint8Array(source);
    const eeprom=values.eeprom?await read(resolve(values.eeprom),64):undefined;
    const configuration=values.configuration?JSON.parse((await read(resolve(values.configuration),65536)).toString('utf8')):{};
    let runtime,translated;
    if(values.translated){
      [runtime,translated]=await Promise.all([read(resolve(values.runtime),PACKAGE_LIMITS.runtime),read(resolve(values.translated),PACKAGE_LIMITS.translated)]);
    }else{
      runtime=await read(new URL('../wasm/attiny13a.wasm',import.meta.url),PACKAGE_LIMITS.runtime);
      const build=JSON.parse((await read(new URL('../wasm/device-build.json',import.meta.url),65536)).toString('utf8'));
      // This is the repository's trusted compiler artifact, not a decoded package.
      if(build.schema!=='micromusic-attiny13a-device-wasm-v1'||build.artifacts?.['attiny13a.wasm']!==hash(runtime))throw new Error('Bundled runtime build integrity mismatch');
      const exports=new WebAssembly.Instance(await WebAssembly.compile(runtime)).exports;
      translated=transpileAVR(flash,runtimeABI(exports,{resumable:!!configuration.resumable}),
        {optimizeFlags:!values['no-flag-dce'],resumable:!!configuration.resumable}).bytes;
    }
    const pkg=await createPackage({flash,eeprom,configuration,translated,runtime});
    const json=JSON.stringify(pkg,null,2)+'\n';
    // Also exercise the public loader before publishing a package file.
    const decoded=await decodePackage(json);
    await writeFile(output,json,{flag:'wx'});
    console.log(JSON.stringify({output,...summary(decoded)},null,2));
    return;
  }
  const input=resolve(args[0]),decoded=await decodePackage((await read(input,PACKAGE_LIMITS.json)).toString('utf8'));
  if(command==='verify'){console.log(JSON.stringify({input,...summary(decoded)},null,2));return;}
  const directory=resolve(args[1]);await mkdir(directory);
  for(const [name,bytes] of [['flash.bin',decoded.flash],['eeprom.bin',decoded.eeprom],['translated.wasm',decoded.translated],['runtime.wasm',decoded.runtime]])await writeFile(resolve(directory,name),bytes,{flag:'wx'});
  for(const [name,value] of [['configuration.json',decoded.configuration],['manifest.json',decoded.manifest],['package-metadata.json',summary(decoded)]])await writeFile(resolve(directory,name),JSON.stringify(value,null,2)+'\n',{flag:'wx'});
  console.log(JSON.stringify({input,directory,...summary(decoded)},null,2));
}
try{await main();}catch(error){console.error(error.message);process.exitCode=1;}
