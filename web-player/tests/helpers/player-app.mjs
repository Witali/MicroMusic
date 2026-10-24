import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';
import {parseHex} from '../../lib/hex.js';
import {RealtimeMonitor} from '../../lib/realtime.js';

export function deferred(){
  let resolve,reject;
  const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});
  return {promise,resolve,reject};
}

// Execute the actual app handlers with a small DOM/media model. This tests
// transport ordering and cancellation; it does not claim browser audio output.
export async function playerApp({speech=true,holdWorklet=false,holdWorker=false,playOnce,prefix='/MicroMusic/',firmware}={}){
  const location=new URL(`https://example.test${prefix}web-player/`);
  if(speech)location.searchParams.set('collection','hq4');
  if(firmware)location.searchParams.set('firmware',firmware);
  const elements=new Map(),selectors=new Map(),workers=[],contexts=[],worklets=[];
  class Element{
    constructor(tag='div',attributes=''){
      this.tagName=tag.toUpperCase();this.textContent='';this.dataset={};this.children=[];
      this.hidden=/\bhidden\b/.test(attributes);this.disabled=/\bdisabled\b/.test(attributes);
      this.checked=/\bchecked\b/.test(attributes);this.value=attributes.match(/\bvalue="([^"]*)"/)?.[1]??'';
      this.attributes=new Map();this.listeners=new Map();this.clientWidth=this.clientHeight=0;
    }
    setAttribute(key,value){this.attributes.set(key,String(value));}
    getAttribute(key){return this.attributes.get(key)??null;}
    removeAttribute(key){this.attributes.delete(key);}
    append(...children){this.children.push(...children);}
    replaceChildren(...children){this.children=children;}
    getContext(){return {};}
    addEventListener(type,listener){const list=this.listeners.get(type)??[];list.push(listener);this.listeners.set(type,list);}
    emit(type){for(const listener of this.listeners.get(type)??[])listener({type,target:this});}
  }
  class Media extends Element{
    constructor(){super('audio');this.paused=true;this.ended=false;this.currentTime=0;this.volume=1;this.plays=0;this.source='';}
    set src(value){this.source=new URL(value,location).href;}
    get src(){return this.source;}
    removeAttribute(key){super.removeAttribute(key);if(key==='src')this.source='';}
    load(){this.paused=true;this.currentTime=0;this.ended=false;}
    play(){this.plays++;this.paused=false;this.ended=false;this.emit('playing');return this.pendingPlay?.promise??Promise.resolve();}
    pause(){this.paused=true;this.emit('pause');}
    finish(){this.paused=true;this.ended=true;this.emit('ended');}
  }
  const html=readFileSync(new URL('../../index.html',import.meta.url),'utf8');
  for(const [,tag,attributes,id] of html.matchAll(/<(\w+)\b([^>]*\bid="([^"]+)"[^>]*)>/g))
    elements.set(id,tag==='audio'?new Media():new Element(tag,attributes));
  const get=id=>{if(!elements.has(id))throw new Error('Missing app element: '+id);return elements.get(id);};
  get('cutoff').value='9000';
  const radio=new Element('input');radio.value='wasm';radio.checked=true;
  const document={body:new Element('body'),getElementById:get,createElement:tag=>new Element(tag),
    querySelector:selector=>{
      if(selector==='input[name="engine"]:checked')return radio;
      if(!selectors.has(selector))selectors.set(selector,new Element());
      return selectors.get(selector);
    },querySelectorAll:selector=>selector==='input[name="engine"]'?[radio]:[],addEventListener(){}};
  const workletSetup=deferred();
  class Context{
    constructor(){this.sampleRate=48000;this.audioWorklet={addModule:()=>holdWorklet?workletSetup.promise:Promise.resolve()};contexts.push(this);}
    async resume(){}async close(){}
  }
  class Worklet{
    constructor(){this.messages=[];this.port={postMessage:message=>this.messages.push(message)};worklets.push(this);}
    connect(){}
  }
  class Worker{
    constructor(){this.messages=[];workers.push(this);}
    terminate(){this.terminated=true;}
    ready(){
      if(!this.terminated)this.onmessage?.({data:{type:'ready',state:{registers:new Uint8Array(32),pc:0,cycles:0,irqs:0,maxISR:0,lost:0}}});
    }
    postMessage(message){
      this.messages.push(message);
      if(message.type==='init'&&!holdWorker)queueMicrotask(()=>this.ready());
    }
  }
  const catalog=JSON.parse(readFileSync(new URL(speech?'../../hq4-firmware.json':'../../firmware.json',import.meta.url)));
  if(playOnce!==undefined){
    // Explicit fixtures use canonical lengths; the catalog suite independently
    // checks the production playOnce and phraseSamples metadata.
    const references=JSON.parse(readFileSync(new URL('../../../ATtiny13A/Sound/audio-references.json',import.meta.url))).clips;
    for(const entry of catalog.entries)if(entry.kind==='speech'){
      entry.playOnce=playOnce;entry.phraseSamples=references.find(clip=>clip.id===entry.audioReferenceId).samples;
    }
  }
  const window={devicePixelRatio:1,AudioContext:Context,addEventListener(){}};
  const sandbox={document,window,location,URL,Float32Array,Uint8Array,console,parseHex,RealtimeMonitor,
    Worker,AudioWorkletNode:Worklet,ResizeObserver:class{observe(){}},
    MessageChannel:class{constructor(){this.port1={};this.port2={};}},
    performance:{now:()=>Date.now()},setTimeout:()=>1,clearTimeout(){},
    history:{replaceState:(_state,_title,url)=>{location.href=String(url);}},
    fetch:async()=>({ok:true,json:async()=>structuredClone(catalog)})};
  const source=readFileSync(new URL('../../app.js',import.meta.url),'utf8')
    .replace(/^import .*;\r?\n/gm,'').replaceAll('import.meta.url',JSON.stringify(location.href));
  await runInNewContext(`(async()=>{${source}\n})()`,sandbox);
  await Promise.resolve();
  function position(frames,extra={}){
    const node=worklets.at(-1),connection=node.messages.findLast(message=>message.type==='connect');
    node.port.onmessage({data:{type:'position',session:connection.session,frames,clockFrames:frames,underruns:0,...extra}});
  }
  return {get,body:document.body,original:get('original-audio'),workers,contexts,worklets,workletSetup,catalog,location,selectors,position};
}
