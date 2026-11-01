import {publishedManifest} from './lpx-manifests.mjs';

// Valid synthetic framing for UI contracts; actual encoder proofs are separate.
export const speexManifest={schemaVersion:1,codec:'Speex NB',decoderTarget:'atmega328p',
  title:publishedManifest.title,sampleRate:8000,samples:19200,durationSeconds:2.4,previewKind:'native-pwm8',
  reference:{audio:'audio/lpx-bread/original.wav'},
  variants:[['compact','Компактный',1,2150,6],['quality','Повышенное качество',3,8000,20]].map(([id,label,mode,nominalBitrateBps,packetBytes])=>({
    id,label,mode,nominalBitrateBps,packetBytes,packets:121,decodedSamples:19360,trimStartSamples:80,trimEndSamples:80,
    audio:'audio/speex-bread/'+id+'.wav',stream:'audio/speex-bread/'+id+'.spxraw',bytes:packetBytes*121,
    bitrateBps:packetBytes*121*8/2.4}))};
