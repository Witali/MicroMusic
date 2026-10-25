// Bundle only a fully audited mono image; browser import uses the same verifier.
import fs from 'node:fs';
import path from 'node:path';
import {universalPackageEntry} from '../web-player/lib/universal-package.js';
const folder=path.resolve(process.argv[2]);
const json=name=>JSON.parse(fs.readFileSync(path.join(folder,name)));
const pkg={schema:'micromusic-um88-package',version:1,
 score:json('score.json'),build:json('build-report.json'),verification:json('verification.json'),
 arrangement:json('arrangement.json'),arrangementReport:json('arrangement-report.json'),
 notices:['FluidR3-MIT.txt','Microchip-device-license.txt'].map(name=>({name,text:fs.readFileSync(path.join(folder,name),'utf8')})),
 flashHex:fs.readFileSync(path.join(folder,'synth.hex'),'utf8')};
await universalPackageEntry(pkg);
fs.writeFileSync(path.join(folder,'player-package.json'),JSON.stringify(pkg,null,2)+'\n');
console.log('Verified mono UM88 package:',folder);
