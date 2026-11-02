import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';

test('vendored AVR8js runtime and legal notice match their pinned provenance; browser copies change only imports',()=>{
  const root=new URL('../vendor/avr8js/0.21.1/',import.meta.url);
  const read=path=>readFileSync(new URL(path,root));
  const hash=data=>createHash('sha256').update(data).digest('hex');
  const provenance=JSON.parse(read('provenance.json'));
  assert.equal(provenance.version,'0.21.1');assert.equal(provenance.license,'MIT');
  assert.equal(Object.keys(provenance.original_sha256).length,6);
  assert.equal(hash(read('LICENSE')),provenance.license_sha256);
  for(const [path,expected] of Object.entries(provenance.original_sha256)){
    const original=read('original/'+path),browser=read('browser/'+path);
    assert.equal(hash(original),expected,path);assert.equal(hash(browser),provenance.browser_sha256[path],path);
    const adapted=original.toString('utf8').replace(/(from ['"])(\.\.?\/[^'"]+)(['"])/g,
      (all,start,target,end)=>target.endsWith('.js')?all:start+target+'.js'+end);
    assert.equal(browser.toString('utf8'),adapted,path);
  }
});
