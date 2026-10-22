import { createServer } from 'node:http';
import { readFile, stat } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { resolve, extname, sep } from 'node:path';
const root=resolve(fileURLToPath(new URL('../../',import.meta.url)));
const port=Number(process.argv[2]||8133);
if (!Number.isInteger(port) || port<1024 || port>65535) throw new Error('Invalid port');
const mime={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.mjs':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.json':'application/json; charset=utf-8','.svg':'image/svg+xml','.wav':'audio/wav','.wasm':'application/wasm','.txt':'text/plain; charset=utf-8','.md':'text/plain; charset=utf-8','.hex':'text/plain; charset=utf-8','.c':'text/plain; charset=utf-8'};
createServer(async(req,res)=>{
  try {
    if (!['GET','HEAD'].includes(req.method)) { res.writeHead(405); res.end(); return; }
    let path=decodeURIComponent(new URL(req.url,'http://localhost').pathname);
    if (path==='/') { res.writeHead(302,{Location:'/web-player/'}); res.end(); return; }
    if (!['/web-player/','/ATtiny13A/Music/','/ATtiny13A/Sound/','/build/hq4-preview/','/i8080/Emulator/','/i8080/CRC/','/i8080/Sound/'].some(prefix=>path.startsWith(prefix))) throw new Error('Not found');
    if (path.endsWith('/')) path+='index.html';
    const target=resolve(root,'.'+path);
    if (!target.startsWith(root+sep) || path.split('/').some(s=>s.startsWith('.'))) throw new Error('Not found');
    if (!(await stat(target)).isFile()) throw new Error('Not found');
    const data=await readFile(target);
    res.writeHead(200,{'Content-Type':mime[extname(target)]||'application/octet-stream','Content-Length':data.length,'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'});
    res.end(req.method==='HEAD' ? undefined : data);
  } catch { res.writeHead(404,{'Content-Type':'text/plain; charset=utf-8'}); res.end('Not found'); }
}).listen(port,'127.0.0.1',()=>console.log(`Local: http://127.0.0.1:${port}/web-player/`));
