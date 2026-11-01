import {coreProbeCases} from './avr-core-probe-cases.mjs';

// Original test vectors, not an arithmetic backend. Expectations use the pinned
// Microchip DS40002198A sections below. I stays clear: this 60-byte mailbox
// reserves only four stack bytes and is not an interrupt experiment.
const flagCases=Object.freeze([
  {id:'adc-new-zero',form:'ADC',manualSection:'5.1',a:0,b:0,flags:0x40,asm:'adc r16,r17',result:0,sreg:0x42,cycles:1},
  {id:'sbc-zero-set',form:'SBC',manualSection:'5.93',a:0,b:0,flags:0x42,asm:'sbc r16,r17',result:0,sreg:0x42,cycles:1},
  {id:'sbc-zero-clear',form:'SBC',manualSection:'5.93',a:0,b:0,flags:0x40,asm:'sbc r16,r17',result:0,sreg:0x40,cycles:1},
  {id:'cpc-zero-clear',form:'CPC',manualSection:'5.46',a:42,b:42,flags:0x40,asm:'cpc r16,r17',result:42,sreg:0x40,cycles:1},
  {id:'cp-overflow',form:'CP',manualSection:'5.45',a:128,b:1,flags:0x40,asm:'cp r16,r17',result:128,sreg:0x78,cycles:1},
  {id:'cpi-borrow',form:'CPI',manualSection:'5.47',a:128,b:0,flags:0x40,asm:'cpi r16,255',result:128,sreg:0x75,cycles:1},
  {id:'and-preserved-hct',form:'AND',manualSection:'5.4',a:240,b:15,flags:0x7d,asm:'and r16,r17',result:0,sreg:0x63,cycles:1},
  {id:'or-preserved-hct',form:'OR',manualSection:'5.82',a:128,b:1,flags:0x7b,asm:'or r16,r17',result:129,sreg:0x75,cycles:1},
  {id:'clr-preserved-hct',form:'EOR',manualSection:'5.54',a:165,b:0,flags:0x7d,asm:'eor r16,r16',result:0,sreg:0x63,cycles:1},
  {id:'inc-preserved-hct',form:'INC',manualSection:'5.61',a:127,b:0,flags:0x61,asm:'inc r16',result:128,sreg:0x6d,cycles:1},
  {id:'dec-preserved-hct',form:'DEC',manualSection:'5.49',a:128,b:0,flags:0x61,asm:'dec r16',result:127,sreg:0x79,cycles:1},
  {id:'neg-minimum',form:'NEG',manualSection:'5.80',a:128,b:0,flags:0x62,asm:'neg r16',result:128,sreg:0x4d,cycles:1},
].map(Object.freeze));
const suites=Object.freeze({
  core:Object.freeze({id:'core',cases:coreProbeCases,
    forms:Object.freeze(['ADD','ADC','SUB','SBC','CPC','LSR','ASR','ROR','ADIW','BRNE','CPSE','RCALL'])}),
  flags:Object.freeze({id:'flags',cases:flagCases,forms:Object.freeze(flagCases.map(c=>c.form))}),
});
export function oracleSuite(name='core'){
  if(!Object.hasOwn(suites,name))throw Error('Unknown oracle suite');
  return suites[name];
}
