// Keep the original bank external; render every semitone used to fit the tables.
import { spawnSync } from 'node:child_process';
const args=Object.fromEntries(process.argv.slice(2).reduce((a,v,i,list)=>i%2?a:[...a,[v.replace(/^--/,''),list[i+1]]],[]));
if (!args.soundfont || !args.engine) throw new Error('Usage: node tools/capture-fluid-grid.mjs --soundfont original.sf2 --engine spessasynth.js');
for (const [profile, first] of [['violin',52],['piano',49],['guitar',44],['drums',null]]) {
  const notes=first===null?'35,38,42':Array.from({length:75-first},(_,i)=>first+i).join(',');
  const result=spawnSync(process.execPath,['tools/render-fluid-violin.mjs','--soundfont',args.soundfont,'--engine',args.engine,
    '--profile',profile,'--notes',notes,'--gate','4','--tail','1.2','--output',`build/fluid-grid/${profile}`],{stdio:'inherit'});
  if(result.status!==0)process.exit(result.status||1);
}
