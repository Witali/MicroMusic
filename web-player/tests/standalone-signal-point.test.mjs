import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync,readdirSync} from 'node:fs';
import {createContext,runInContext} from 'node:vm';

const root=new URL('../../',import.meta.url),read=path=>readFileSync(new URL(path,root),'utf8').replace(/\r\n/g,'\n');
const ui=html=>html.match(/let audio(?:=|,)[\s\S]*?(?=<\/script>)/)[0];
const names=readdirSync(new URL('ATtiny13A/Music/variants/',root)).filter(name=>{
  try{return !!read(`ATtiny13A/Music/variants/${name}/player.html`);}catch{return false;}
});

// A routing/DOM model, not a replacement for a browser or a Web Audio DSP test.
// Analysers return known distinct channel data so we can identify graph sources.
function standalone(html){
  const elements=new Map(),contexts=[],timers=new Map();let nextTimer=1;
  for(const [,tag,id] of html.matchAll(/<(\w+)\b[^>]*\bid="([^"]+)"[^>]*>/g)){
    const drawing={beginPath(){this.path=[];},moveTo(x,y){this.path.push([x,y]);},lineTo(x,y){this.path.push([x,y]);},
      stroke(){this.plotted=this.path;},fillRect(){}};
    elements.set(id,{value:id==='volume'?'0.65':id==='signal-point'?'output':'',width:900,height:180,clientWidth:900,
      attributes:{},setAttribute(key,value){this.attributes[key]=value;},getContext(){return drawing;},drawing});
  }
  class Node{
    constructor(context,kind){this.context=context;this.kind=kind;this.connections=[];this.gain={value:1};this.frequency={value:0};this.Q={value:0};context.nodes.push(this);}
    connect(target,output=0,input=0){this.connections.push({target,output,input});return target;}
    disconnect(){this.connections=[];}
    getFloatTimeDomainData(array){array.fill(this.channel===1?-.375:.25);}
  }
  class Audio{
    constructor(){this.nodes=[];this.sampleRate=48000;this.destination=new Node(this,'destination');contexts.push(this);}
    createScriptProcessor(){this.processor=new Node(this,'processor');return this.processor;}
    createBiquadFilter(){return new Node(this,'filter');}
    createGain(){return new Node(this,'gain');}
    createAnalyser(){const node=new Node(this,'analyser');node.channel=this.nodes.filter(n=>n.kind==='analyser').length-1;return node;}
    createChannelSplitter(){return new Node(this,'splitter');}
    createChannelMerger(){return new Node(this,'merger');}
    async resume(){}async close(){this.closed=true;}
  }
  const context=createContext({document:{getElementById:id=>elements.get(id),addEventListener(){}},
    window:{AudioContext:Audio},AudioContext:Audio,devicePixelRatio:1,console,
    setInterval:callback=>{const id=nextTimer++;timers.set(id,callback);return id;},clearInterval:id=>timers.delete(id)});
  for(const [,script] of html.matchAll(/<script>\s*([\s\S]*?)<\/script>/g))runInContext(script,context);
  return {get:id=>elements.get(id),contexts,timers,
    value:source=>runInContext(source,context),
    frame(channels){
      const data=Array.from({length:channels},()=>new Float32Array(4096));
      contexts.at(-1).processor.onaudioprocess({outputBuffer:{length:4096,getChannelData:ch=>data[ch]}});
      for(const timer of timers.values())timer();return data;
    }};
}
function activePaths(context){
  const result=[];
  function visit(node,path){
    if(node.kind==='gain'&&node.gain.value===0)return;
    path=[...path,node];if(node===context.destination){result.push(path);return;}
    for(const {target} of node.connections)visit(target,path);
  }
  visit(context.processor,[]);return result;
}

for(const name of names)test(name+': offline selector routes audio and draws OCR or filtered analyser data without restarting firmware',async()=>{
  const folder=`ATtiny13A/Music/variants/${name}/`,html=read(folder+'player.html'),stereo=name==='lumiere-stereo';
  const template=read(stereo?'tools/stereo-player-template.html':'tools/player-template.html');
  assert.match(html,/<option value="output" selected>/);
  assert.equal(ui(html),stereo?ui(template):ui(template).replace('lp.frequency.value=4000',`lp.frequency.value=${name.endsWith('-sparse')||name.endsWith('-polyphonic')?9000:4000}`));
  assert.equal(html.match(/const FIRMWARE_HEX = `([\s\S]*?)`;/)[1].trim(),read(folder+'synth.hex').trim());
  assert.equal(html.match(/const EEPROM_HEX = `([\s\S]*?)`;/)[1].trim(),read(folder+'eeprom.hex').trim());
  const app=standalone(html),select=app.get('signal-point');
  assert.equal(select.value,'output');
  await app.get(stereo?'play':'start').onclick();
  const context=app.contexts[0],processor=context.processor,core=app.value(stereo?'renderer.core':'core');
  const paths=activePaths(context);assert.equal(paths.length,stereo?2:1);
  for(const path of paths){assert.equal(path.filter(n=>n.kind==='filter').length,2);assert.equal(path.filter(n=>n.kind==='analyser').length,1);}
  const first=app.frame(stereo?2:1),firstCycles=core.cyc;
  for(let ch=0;ch<(stereo?2:1);ch++){
    const canvas=app.get(stereo?(ch?'right':'left'):'wave');
    const value=ch===1?-.375:.25,expected=canvas.height/2-value*canvas.height*(stereo?.43:.42);
    assert.equal(canvas.drawing.plotted[0][1],expected);
  }
  select.value='input';select.onchange();
  assert.equal(core.cyc,firstCycles);assert.equal(context.processor,processor);assert.equal(app.contexts.length,1);
  assert.match(app.get('scope-note').textContent,/OCR/);
  for(const path of activePaths(context))assert.equal(path.filter(n=>n.kind==='filter').length,0);
  for(let ch=0;ch<(stereo?2:1);ch++){
    const canvas=app.get(stereo?(ch?'right':'left'):'wave');
    assert.equal(canvas.drawing.plotted[0][1],canvas.height/2-first[ch][0]*canvas.height*(stereo?.43:.42));
  }
  app.frame(stereo?2:1);assert.ok(core.cyc>firstCycles);
  app.get('volume').value='.2';app.get('volume').oninput();
  for(const path of activePaths(context))assert.ok(path.some(n=>n.kind==='gain'&&n.gain.value===.2));
  const cycles=core.cyc;select.value='output';select.onchange();assert.equal(core.cyc,cycles);
  for(const path of activePaths(context))assert.equal(path.filter(n=>n.kind==='filter').length,2);
  if(stereo){
    const analysers=context.nodes.filter(n=>n.kind==='analyser');
    assert.deepEqual(analysers.map(n=>n.connections[0].input),[0,1]);
  }
  await app.get('stop').onclick();assert.equal(app.timers.size,0);assert.ok(context.closed);
});
