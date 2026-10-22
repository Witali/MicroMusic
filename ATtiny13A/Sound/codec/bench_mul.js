'use strict';
const fs=require('fs'),cp=require('child_process'),path=require('path');
const {AVRCore}=require('./avr_emulator.js');
function label(obj,name){let s=cp.execFileSync('llvm-objdump',['--syms',obj],{encoding:'utf8'});let line=s.split('\n').find(s=>s.trim().endsWith(' '+name));if(!line)throw Error('symbol not found '+name);return parseInt(line.trim().slice(0,8),16)/2}
let data={};
for(const [title,folder] of [['before',__dirname+'/reference/chego'],['after',__dirname+'/chego']]){
  let pc=label(folder+'/firmware.o','mul_q4'), bin=fs.readFileSync(folder+'/firmware.bin');
  data[title]={pc,bin, byCoefficient:{}, sumCycles:0, sumInstr:0};
}
let tests=0,miss=0,first=[];
for(let c=-8;c<=7;c++){
 let metrics={};
 for(let x=-128;x<=127;x++){
  let results=[];
  for(const [name,config] of Object.entries(data)){
   let a=new AVRCore(config.bin);a.r[21]=x&255;a.r[23]=c&255;a.pc=config.pc;a.push(0x1f0);let n=0;
   while(a.pc!==0x1f0&&n<200){a.step();n++}
   if(n>=200)throw Error('runaway '+name+' x='+x+' k='+c);
   config.sumCycles+=a.cycles;config.sumInstr+=n;
   results.push({result:a.r[24],cycles:a.cycles,instr:n});
   (metrics[name]??={cycles:0,min:Infinity,max:0,instr:0}).cycles+=a.cycles;
   metrics[name].min=Math.min(metrics[name].min,a.cycles);
   metrics[name].max=Math.max(metrics[name].max,a.cycles);
   metrics[name].instr+=n;
  }
  tests++;
  if(results[0].result!==results[1].result){miss++;if(first.length<6)first.push({x,c,results})}
 }
 for(const [name,v] of Object.entries(metrics))data[name].byCoefficient[c]={averageCycles:v.cycles/256,minCycles:v.min,maxCycles:v.max};
}
console.log(JSON.stringify({cases:tests,diffs:miss,first,baseline:{codeBytes:410,routineBytes:42,averageCycles:data.before.sumCycles/tests,details:data.before.byCoefficient},optimized:{codeBytes:406,routineBytes:38,averageCycles:data.after.sumCycles/tests,details:data.after.byCoefficient}},null,2));
if(miss)process.exitCode=1;
