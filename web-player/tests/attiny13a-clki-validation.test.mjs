import {test} from 'node:test';
import assert from 'node:assert/strict';
import {compileAnalog} from './analog-test-build.mjs';

const make=compileAnalog('attiny13a-clki-validation',[
  'web-player/native/devices/attiny13a/clki_validation.c',
],String.raw`
#include "../devices/attiny13a/clki_validation.h"
#include <stddef.h>
#include <string.h>
#define CHECK(x) do{if(!(x))return __LINE__;}while(0)
static attiny13a_clki_validation_t s,before;
static void snapshot(void){memcpy(&before,&s,sizeof s);}
static int unchanged(void){return !memcmp(&before,&s,sizeof s);}
static uint32_t edge(uint64_t at,uint8_t level,int32_t vcc,int held){return attiny13a_clki_validation_edge(&s,at,level,vcc,held);}
static uint32_t periods(uint64_t previous,uint64_t current) {
 if(attiny13a_clki_validation_init(&s,0,0,0)||edge(1,1,5000000,0)||
    edge(1+previous/2,0,5000000,0)||edge(1+previous,1,5000000,0)||
    edge(1+previous+current/2,0,5000000,0))return UINT32_MAX;
 return edge(1+previous+current,1,5000000,0);
}
int all_voltage_tier_boundaries_and_widths(void) {
 const int32_t vcc[]={1800000,2699999,2700000,4499999,4500000,5500000};
 const uint64_t widths[]={100000,100000,40000,40000,20000,20000};
 for(unsigned i=0;i<6;i++)for(unsigned polarity=0;polarity<2;polarity++)for(int delta=-1;delta<=1;delta++) {
  CHECK(!attiny13a_clki_validation_init(&s,0,(uint8_t)!polarity,0));
  CHECK(!edge(1,(uint8_t)polarity,vcc[i],0));
  uint32_t expected=delta<0?(polarity?AT13_CLKI_VALIDATION_HIGH:AT13_CLKI_VALIDATION_LOW):0;
  CHECK(edge(1+widths[i]+delta,(uint8_t)!polarity,vcc[i],0)==expected);
 }
 return 0;
}
int all_voltage_tier_period_boundaries(void) {
 const int32_t vcc[]={1800000,2699999,2700000,4499999,4500000,5500000};
 const uint64_t periods[]={250000,250000,100000,100000,50000,50000};
 const uint64_t widths[]={100000,100000,40000,40000,20000,20000};
 for(unsigned i=0;i<6;i++)for(int delta=-1;delta<=1;delta++) {
  CHECK(!attiny13a_clki_validation_init(&s,0,0,0));
  CHECK(!edge(1,1,vcc[i],0)&&!edge(1+widths[i],0,vcc[i],0));
  CHECK(edge(1+periods[i]+delta,1,vcc[i],0)==(delta<0?AT13_CLKI_VALIDATION_PERIOD:0));
  CHECK(s.previous_period_ps==periods[i]+delta);
 }
 return 0;
}
int voltage_outside_the_characterized_range_is_explicit(void) {
 const int32_t invalid[]={-1,0,1799999,5500001,INT32_MAX};
 for(unsigned i=0;i<5;i++) {
  CHECK(!attiny13a_clki_validation_init(&s,0,0,0));
  CHECK(edge(1,1,invalid[i],0)==AT13_CLKI_VALIDATION_VOLTAGE);
  CHECK(s.previous_edge_ps==1&&s.level==1&&s.violations==AT13_CLKI_VALIDATION_VOLTAGE);
 }
 return 0;
}
int initial_partial_intervals_are_unknown(void) {
 for(uint8_t level=0;level<2;level++) {
  CHECK(!attiny13a_clki_validation_init(&s,100,level,0));
  CHECK(!edge(101,(uint8_t)!level,5000000,0));
  CHECK(!edge(20101,level,5000000,0));
  CHECK(s.have_edge&&s.have_rise&&!s.previous_period_ps&&!s.violations);
 }
 return 0;
}
int both_variation_interpretations_are_exact(void) {
 CHECK(periods(100000,102000)==0);CHECK(periods(100000,102001)==AT13_CLKI_VALIDATION_VARIATION);
 CHECK(periods(102000,100000)==0);CHECK(periods(102001,100000)==AT13_CLKI_VALIDATION_VARIATION);
 CHECK(periods(100000,98040)==0);CHECK(periods(100000,98039)==AT13_CLKI_VALIDATION_VARIATION);
 CHECK(periods(100000,98000)==AT13_CLKI_VALIDATION_VARIATION); // period-only2% would pass.
 CHECK(periods(100001,102001)==0);CHECK(periods(100001,102002)==AT13_CLKI_VALIDATION_VARIATION);
 return 0;
}
int reset_discards_spanning_variation_baselines(void) {
 CHECK(!attiny13a_clki_validation_init(&s,0,0,0));
 CHECK(!edge(1,1,5000000,0)&&!edge(50001,0,5000000,0)&&!edge(100001,1,5000000,0));
 CHECK(s.have_comparison_period&&s.comparison_period_ps==100000);
 CHECK(!attiny13a_clki_validation_set_reset(&s,110000,1));
 CHECK(!s.have_comparison_period&&!s.have_comparison_rise&&s.have_rise&&s.previous_rise_ps==100001);
 CHECK(!edge(200001,0,5000000,1)&&!edge(400001,1,5000000,1));
 CHECK(!s.have_comparison_period&&s.previous_period_ps==300000);
 CHECK(!attiny13a_clki_validation_set_reset(&s,410000,0));
 CHECK(!edge(450001,0,5000000,0)&&!edge(500001,1,5000000,0));
 CHECK(!s.have_comparison_period&&s.have_comparison_rise); // excludes period spanning Reset.
 CHECK(!edge(550001,0,5000000,0)&&!edge(600001,1,5000000,0));
 CHECK(s.have_comparison_period&&s.comparison_period_ps==100000);
 CHECK(!edge(650001,0,5000000,0)&&!edge(702001,1,5000000,0)); // exact permitted expansion.
 CHECK(!edge(750001,0,5000000,0));
 CHECK(edge(810001,1,5000000,0)==AT13_CLKI_VALIDATION_VARIATION);
 return 0;
}
int reset_never_exempts_physical_limits(void) {
 CHECK(!attiny13a_clki_validation_init(&s,0,0,0));
 CHECK(!edge(1,1,5000000,0)&&!edge(25001,0,5000000,0)&&!edge(50001,1,5000000,0));
 CHECK(!attiny13a_clki_validation_set_reset(&s,50001,1));
 CHECK(edge(60001,0,5000000,1)==AT13_CLKI_VALIDATION_HIGH);
 CHECK(edge(70001,1,5000000,1)==(AT13_CLKI_VALIDATION_LOW|AT13_CLKI_VALIDATION_PERIOD));
 CHECK(!(s.violations&AT13_CLKI_VALIDATION_VARIATION));
 CHECK(edge(80001,0,1000000,1)==AT13_CLKI_VALIDATION_VOLTAGE);
 return 0;
}
int same_reset_state_keeps_comparison_history(void) {
 CHECK(!attiny13a_clki_validation_init(&s,0,0,0));
 CHECK(!edge(1,1,5000000,0)&&!edge(50001,0,5000000,0)&&!edge(100001,1,5000000,0));
 CHECK(!edge(150001,0,5000000,0));
 CHECK(!attiny13a_clki_validation_set_reset(&s,175001,0)&&s.have_comparison_period);
 CHECK(!edge(200001,1,5000000,0)&&!edge(225001,0,5000000,0));
 CHECK(edge(400001,1,5000000,0)==AT13_CLKI_VALIDATION_VARIATION);
 return 0;
}
int edge_reset_argument_also_changes_baseline(void) {
 CHECK(periods(100000,100000)==0);
 CHECK(!edge(250001,0,5000000,1));CHECK(!s.have_comparison_period);
 CHECK(!edge(400001,1,5000000,1));
 CHECK(!edge(450001,0,5000000,0));CHECK(!s.have_comparison_rise);
 CHECK(!edge(500001,1,5000000,0)&&!s.have_comparison_period);
 return 0;
}
int observations_remain_exact_above2pow53_and_near_max(void) {
 const uint64_t start=(UINT64_C(1)<<53)+37;
 CHECK(!attiny13a_clki_validation_init(&s,start,0,1));
 CHECK(!edge(start+1,1,5000000,1));
 CHECK(!edge(start+50001,0,5000000,1));
 CHECK(!edge(UINT64_MAX-1,1,5000000,1));
 CHECK(s.now_ps==UINT64_MAX-1&&s.previous_period_ps==UINT64_MAX-1-(start+1));
 CHECK(!s.violations);snapshot();
 CHECK(edge(UINT64_MAX,0,5000000,1)==AT13_CLKI_VALIDATION_MALFORMED&&unchanged());
 CHECK(attiny13a_clki_validation_set_reset(&s,UINT64_MAX,0)==AT13_CLKI_VALIDATION_MALFORMED&&unchanged());
 CHECK(!attiny13a_clki_validation_init(&s,0,0,0));
 CHECK(!edge(1,1,5000000,0)&&!edge(25001,0,5000000,0)&&!edge(50001,1,5000000,0));
 CHECK(!edge(75001,0,5000000,0));
 CHECK(edge(UINT64_MAX-1,1,5000000,0)==AT13_CLKI_VALIDATION_VARIATION);
 return 0;
}
int hold_has_no_maximum_and_restart_is_diagnostic(void) {
 CHECK(periods(100000,100000)==0);CHECK(!edge(250001,0,5000000,0));
 CHECK(!attiny13a_clki_validation_set_reset(&s,UINT64_C(1000000000000000),0));
 CHECK(edge(UINT64_C(1000000000000001),1,5000000,0)==AT13_CLKI_VALIDATION_VARIATION);
 CHECK(!(s.violations&(AT13_CLKI_VALIDATION_HIGH|AT13_CLKI_VALIDATION_LOW|AT13_CLKI_VALIDATION_PERIOD)));
 return 0;
}
int electrical_reasons_update_history_and_stay_observable(void) {
 CHECK(!attiny13a_clki_validation_init(&s,0,0,0));CHECK(!edge(1,1,5000000,0));
 CHECK(edge(2,0,5000000,0)==AT13_CLKI_VALIDATION_HIGH);
 CHECK(s.now_ps==2&&s.level==0&&s.previous_edge_ps==2&&s.violations==AT13_CLKI_VALIDATION_HIGH);
 CHECK(!edge(50001,1,5000000,0));CHECK(s.violations==AT13_CLKI_VALIDATION_HIGH);
 CHECK(!attiny13a_clki_validation_init(&s,0,0,0)&&!s.violations);
 return 0;
}
int malformed_observations_are_atomic(void) {
 CHECK(!attiny13a_clki_validation_init(&s,10,0,0));snapshot();
 CHECK(edge(10,1,5000000,0)==AT13_CLKI_VALIDATION_MALFORMED&&unchanged());
 CHECK(edge(9,1,5000000,0)==AT13_CLKI_VALIDATION_MALFORMED&&unchanged());
 CHECK(edge(11,0,5000000,0)==AT13_CLKI_VALIDATION_MALFORMED&&unchanged());
 CHECK(edge(11,2,5000000,0)==AT13_CLKI_VALIDATION_MALFORMED&&unchanged());
 CHECK(edge(11,1,5000000,2)==AT13_CLKI_VALIDATION_MALFORMED&&unchanged());
 CHECK(attiny13a_clki_validation_init(&s,UINT64_MAX,0,0)==AT13_CLKI_VALIDATION_MALFORMED&&unchanged());
 CHECK(attiny13a_clki_validation_init(&s,0,2,0)==AT13_CLKI_VALIDATION_MALFORMED&&unchanged());
 CHECK(attiny13a_clki_validation_init(&s,0,0,-1)==AT13_CLKI_VALIDATION_MALFORMED&&unchanged());
 CHECK(attiny13a_clki_validation_set_reset(&s,9,0)==AT13_CLKI_VALIDATION_MALFORMED&&unchanged());
 CHECK(!edge(11,1,5000000,0));CHECK(!attiny13a_clki_validation_set_reset(&s,100,0));snapshot();
 CHECK(edge(99,0,5000000,0)==AT13_CLKI_VALIDATION_MALFORMED&&unchanged());
 CHECK(edge(11,0,5000000,0)==AT13_CLKI_VALIDATION_MALFORMED&&unchanged());
 CHECK(!attiny13a_clki_validation_set_reset(&s,20100,0));
 CHECK(!edge(20100,0,5000000,0)); // same-time Reset/edge is allowed, not a duplicate physical edge.
 CHECK(attiny13a_clki_validation_init(NULL,0,0,0)==AT13_CLKI_VALIDATION_MALFORMED);
 CHECK(attiny13a_clki_validation_set_reset(NULL,0,0)==AT13_CLKI_VALIDATION_MALFORMED);
 CHECK(attiny13a_clki_validation_edge(NULL,1,1,5000000,0)==AT13_CLKI_VALIDATION_MALFORMED);
 return 0;
}
`);
const cases={
  all_voltage_tier_boundaries_and_widths:'all VCC tier endpoints check high/low widths at minus1/exact/plus1ps',
  all_voltage_tier_period_boundaries:'all VCC tiers check period at minus1/exact/plus1ps',
  voltage_outside_the_characterized_range_is_explicit:'out-of-range supply returns explicit uncertainty',
  initial_partial_intervals_are_unknown:'initial partial widths and periods are not invented',
  both_variation_interpretations_are_exact:'both2% interpretations use exact conservative integer limits',
  reset_discards_spanning_variation_baselines:'Reset clears comparison origins without reusing spanning periods',
  reset_never_exempts_physical_limits:'Reset does not exempt voltage/pulse/period limits',
  same_reset_state_keeps_comparison_history:'same-state Reset polls cannot disable comparison',
  edge_reset_argument_also_changes_baseline:'edge-provided effective Reset updates comparison state',
  observations_remain_exact_above2pow53_and_near_max:'large timestamps/periods remain exact without overflow',
  hold_has_no_maximum_and_restart_is_diagnostic:'holds have no maximum and restart variation remains explicit',
  electrical_reasons_update_history_and_stay_observable:'physical violations update history and accumulate distinct reasons',
  malformed_observations_are_atomic:'malformed observations reject atomically and permit recovery',
};
for(const [name,description] of Object.entries(cases))test('ATtiny13A CLKI validation: '+description,()=>{
  const line=make()[name]();assert.equal(line,0,`${name}: C assertion at line ${line}`);
});
