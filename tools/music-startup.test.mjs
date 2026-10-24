import {test} from 'node:test';
import {auditVariant,baseline,engines} from './audit-music-startup.mjs';
for(const name of Object.keys(baseline.variants))for(const engine of engines)
  test(`${engine[0]} / ${engine[1]} / ${name}: datasheet pin order and identical musical continuation`,()=>auditVariant(name,engine));
