/* Offline JS behavior test with fake canvas and audio device.
 * Chromium is not reachable in this execution sandbox; hardware audio is not tested.
 */
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync(__dirname+'/index.html','utf8');
const script=html.match(/<script>([\s\S]*?)<\/script>/)[1];
const elements={};
function elem(id){if(!elements[id])elements[id]={id,value:id==='clip'?'chego':id==='variant'?'hq':'',textContent:'',style:{},disabled:false,
 getContext:()=>new Proxy({}, {get:(_p,key)=>['stroke','beginPath','moveTo','lineTo','fillRect','clearRect'].includes(key)?()=>{}:undefined}),
 width:900,height:140};return elements[id]}
class FakeCtx{constructor(){this.currentTime=.01;this.destination={};this.sampleRate=48000}async resume(){}createBuffer(_n,len,rate){return{duration:len/rate,getChannelData:()=>new Float32Array(len)}}createBufferSource(){return{buffer:null,connect(){return this},start(){},stop(){}}}createGain(){return {gain:{value:1},connect(){return this}}}}
const ctx={window:{AudioContext:FakeCtx},document:{getElementById:elem,createElement:()=>({click(){},remove(){}}),body:{appendChild(){}}},console,
 atob:s=>Buffer.from(s,'base64').toString('binary'),setTimeout,URL:{createObjectURL(){return'blob:x'},revokeObjectURL(){}},Blob:class{},Float32Array,Uint8Array,DataView,Math,Number,JSON,Promise};
vm.runInNewContext(script,ctx,{timeout:10000});
(async()=>{
 let count=0;for(const v of ['chego','otvechaesh','vinni']){
  elem('clip').value=v;elem('clip').onchange();
  for(const mode of ['original','lpx3','old','hq']){
   elem('variant').value=mode;elem('variant').onchange();
   await elem('play').onclick();await elem('ab').onclick();
   assert(!elem('status').textContent.includes('Ошибка'),v+' '+mode+' '+elem('status').textContent);
   count++;
  }
  elem('variant').value='hq';elem('variant').onchange();
  await elem('verify').onclick();
  const result=elem('verifyStats').textContent;
  assert(result.includes('Расхождения с проверенным WAV: 0'),v+' '+result);
  assert(result.includes('Пропуски Timer0: 0'),v);
  assert(result.includes('Запоздавшие отсчёты: 0'),v);
  console.log(v,result.split('\n').join('; '));
 }
 console.log('OK UI smoke,',count,'playback selections, 3 AVR verification operations');
})().catch(e=>{console.error(e);process.exitCode=1});
