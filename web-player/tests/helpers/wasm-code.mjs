// Small independent readers for assertions about emitted WASM function bodies.
export function bodyList(bytes){
  let p=8;const u32=()=>{let n=0;for(let shift=0;shift<35;shift+=7){const b=bytes[p++];n+=(b&127)*2**shift;if(!(b&128))return n;}throw Error('Invalid test WASM');};
  while(p<bytes.length){const id=bytes[p++],size=u32(),end=p+size;
    if(id===10)return Array.from({length:u32()},()=>{const n=u32(),body=Buffer.from(bytes.subarray(p,p+n));p+=n;return body;});p=end;}
  throw Error('Missing code section');
}
export function addressBytes(value){const out=[0x41];let more;
  do{const b=value&127;value>>=7;more=!((value===0&&!(b&64))||(value===-1&&(b&64)));out.push(b|(more?128:0));}while(more);return out;
}
export function occurrences(body,needle){let n=0;for(let p=0;(p=body.indexOf(needle,p))>=0;p+=needle.length)n++;return n;}
