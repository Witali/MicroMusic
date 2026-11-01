import {readFileSync} from 'node:fs';

export const publishedManifest=JSON.parse(readFileSync(new URL('../../audio/lpx-bread/manifest.json',import.meta.url)));
// Retain the original two-variant schema after the published manifest grows.
export const legacyManifest={...publishedManifest,codec:'LPX v5',
  variants:publishedManifest.variants.filter(variant=>['compact','quality'].includes(variant.id)).map(({flashMeasurement,...variant})=>variant)};
// Synthetic metadata for UI/schema contracts, independent of encoder outcomes.
export const low15Fixture={id:'low15',label:'Очень низкий битрейт',profile:15,codec:'lpx-s15',formatVersion:8,
  audio:'audio/lpx-bread/low15.wav',stream:'audio/lpx-bread/low15.lpx',bytes:432,bitrateBps:1440};
export const threeVariantManifest={...legacyManifest,codec:'LPX',variants:[...legacyManifest.variants,low15Fixture]};
