// Construction-time storage only. No CPU instruction or peripheral callback
// enters IndexedDB. Denial, blocked upgrades and quota failures are recoverable.
export const AVR_CACHE_DATABASE='micromusic-avr-translations-v1';
const encoder=new TextEncoder();
function recordBytes(value){
  if(typeof value==='string')return encoder.encode(value).length;
  if(value&&typeof value.metadata==='string'&&value.bytes instanceof Uint8Array)
    return encoder.encode(value.metadata).length+value.bytes.byteLength;
  throw Error('AVR cache expects metadata and WASM bytes');
}
export function createIndexedDBTranslationStore({indexedDB:provided,
  name=AVR_CACHE_DATABASE,maxEntries=8,maxBytes=16*1024*1024,timeoutMs=1000,now=Date.now}={}){
  let indexedDB=provided;
  if(indexedDB===undefined)try{indexedDB=globalThis.indexedDB;}catch{return null;}
  if(!indexedDB)return null;
  if(!Number.isInteger(maxEntries)||maxEntries<1||maxEntries>64||
    !Number.isSafeInteger(maxBytes)||maxBytes<1||!Number.isInteger(timeoutMs)||timeoutMs<1)
    throw Error('Invalid AVR cache storage limits');
  let opening;
  function open(){
    if(opening)return opening;
    opening=new Promise((resolve,reject)=>{
      let done=false,request;
      const finish=(error,db)=>{if(done){db?.close();return;}done=true;clearTimeout(timer);error?reject(error):resolve(db);};
      const timer=setTimeout(()=>finish(Error('AVR cache open timeout')),timeoutMs);
      try{request=indexedDB.open(name,1);}catch(e){finish(e);return;}
      request.onupgradeneeded=()=>{
        if(done){request.transaction.abort();return;}
        if(!request.result.objectStoreNames.contains('translations'))request.result.createObjectStore('translations',{keyPath:'key'});
      };
      request.onblocked=()=>finish(Error('AVR cache upgrade blocked'));
      request.onerror=()=>finish(request.error??Error('AVR cache open failed'));
      request.onsuccess=()=>{
        const db=request.result;db.onversionchange=()=>{db.close();opening=undefined;};finish(null,db);
      };
    });
    opening.catch(()=>{opening=undefined;});return opening;
  }
  async function transaction(action){
    const db=await open();
    return new Promise((resolve,reject)=>{
      let tx,result,done=false;
      const finish=error=>{if(done)return;done=true;clearTimeout(timer);error?reject(error):resolve(result);};
      const timer=setTimeout(()=>{try{tx?.abort();}catch{}finish(Error('AVR cache transaction timeout'));},timeoutMs);
      try{
        tx=db.transaction('translations','readwrite');
        tx.oncomplete=()=>finish();tx.onabort=()=>finish(tx.error??Error('AVR cache transaction aborted'));
        tx.onerror=()=>{};
        action(tx.objectStore('translations'),value=>{result=value;});
      }catch(e){try{tx?.abort();}catch{}finish(e);}
    });
  }
  return {
    async get(key){return transaction((store,set)=>{
      const request=store.get(key);
      request.onsuccess=()=>{
        const row=request.result;
        if(!row){set(null);return;}
        const value=row.value??row.text;let bytes;
        try{bytes=recordBytes(value);}catch{store.delete(key);set(null);return;}
        if(bytes>maxBytes){store.delete(key);set(null);return;}
        store.put({...row,bytes,usedAt:Math.max(now(),(row.usedAt||0)+1)});set(value);
      };
    });},
    async put(key,value){
      const bytes=recordBytes(value);
      if(bytes>maxBytes)return false;
      value=typeof value==='string'?value:{metadata:value.metadata,bytes:new Uint8Array(value.bytes)};
      return transaction((store,set)=>{
        store.put({key,value,bytes,usedAt:now()});
        const request=store.getAll();
        request.onsuccess=()=>{
          const rows=request.result.sort((a,b)=>a.key===key?1:b.key===key?-1:
            (a.usedAt||0)-(b.usedAt||0)||String(a.key).localeCompare(String(b.key)));
          const weight=row=>Number.isSafeInteger(row.bytes)&&row.bytes>=0?row.bytes:maxBytes+1;
          let total=rows.reduce((sum,row)=>sum+weight(row),0),count=rows.length;
          for(const row of rows){if(count<=maxEntries&&total<=maxBytes)break;store.delete(row.key);total-=weight(row);count--;}
          set(true);
        };
      });
    },
    async delete(key){return transaction((store,set)=>{store.delete(key);set(true);});},
    async close(){if(opening){try{(await opening).close();}catch{}opening=undefined;}},
  };
}
