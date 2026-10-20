import { spawnSync } from 'node:child_process';
const args=Object.fromEntries(process.argv.slice(2).reduce((a,v,i,list)=>i%2?a:[...a,[v.replace(/^--/,''),list[i+1]]],[]));
if(!args.soundfont||!args.engine)throw Error('Specify --soundfont and --engine');
for(const [name,program]of [['violin',40],['fiddle',110],['viola',41],['strings',48],['slow-strings',49]]){
  const r=spawnSync(process.execPath,['tools/render-fluid-violin.mjs','--soundfont',args.soundfont,'--engine',args.engine,
    '--profile','violin','--program',String(program),'--notes','52,55,59,62,66,69,74','--gate','1.2','--tail','.6','--output',`build/fluid-comparison/${name}`],{stdio:'inherit'});
  if(r.status!==0)process.exit(r.status||1);
}
