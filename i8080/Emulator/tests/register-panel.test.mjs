import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';

const source=readFileSync(new URL('../app.mjs',import.meta.url),'utf8');
const update=source.slice(source.indexOf('function updateRegisters('),source.indexOf('\nfunction clearResult('));
class Element {
  constructor(){this.children=[];this.dataset={};this.textContent='';}
  append(...nodes){this.children.push(...nodes);}
  replaceChildren(...nodes){this.children=nodes;}
}
function render(snapshot){
  const nodes=Object.fromEntries(['registers','flags','cpu-status','write-note'].map(id=>[id,new Element()]));
  runInNewContext(update+'\nupdateRegisters(snapshot);',{
    snapshot,$:id=>nodes[id],document:{createElement:()=>new Element()},
    hex:(value,width=2)=>value.toString(16).toUpperCase().padStart(width,'0'),number:String,
  });
  return nodes;
}
test('Register display starts with AF and retains the CPU register/flag values',()=>{
  const nodes=render({registers:[0xb1,0xc2,0xd3,0xe4,0x15,0x26,0x66,0xa7],flags:0xd7,
    pc:0x1234,sp:0xfedc,inte:1,memWrites:12,ignoredWrites:8});
  assert.deepEqual(nodes.registers.children.map(node=>node.children[0].textContent),['A','F','B','C','D','E','H','L']);
  assert.deepEqual(nodes.registers.children.map(node=>node.children[1].textContent),['A7','D7','B1','C2','D3','E4','15','26']);
  assert.deepEqual(nodes.registers.children.map(node=>node.dataset.register),['A','F','B','C','D','E','H','L']);
  assert.equal(nodes['cpu-status'].textContent,'PC 1234 · SP FEDC · INTE 1');
});
test('Reset keeps AF first, zeroes registers and displays the reset flag byte02',()=>{
  const nodes=render(null);
  assert.deepEqual(nodes.registers.children.map(node=>node.children[1].textContent),['00','02','00','00','00','00','00','00']);
  assert.deepEqual(nodes.registers.children.map(node=>node.dataset.register),['A','F','B','C','D','E','H','L']);
});
