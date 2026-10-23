import {test} from 'node:test';
import assert from 'node:assert/strict';
import {compileAnalog} from './analog-test-build.mjs';

const make=compileAnalog('attiny13a-reset-input',[
  'web-player/native/devices/attiny13a/reset_input.c',
  'web-player/native/peripherals/power_reset.c',
],String.raw`
#include "../devices/attiny13a/reset_input.h"
#include "power_reset.h"
#include <stddef.h>
#include <limits.h>
#define CHECK(expression) do { if (!(expression)) return __LINE__; } while (0)
static const attiny13a_reset_input_profile_t profile={300000,500000,100,200,30,40};
static attiny13a_reset_input_t r;
static int init(int32_t pin,int32_t vcc) { return attiny13a_reset_input_init(&r,&profile,0,pin,vcc); }
static int set(uint64_t at,int32_t pin,int32_t vcc) { return attiny13a_reset_input_set_voltage(&r,at,pin,vcc); }
static int advance(uint64_t at) { return attiny13a_reset_input_advance(&r,at); }
static uint64_t next(void) { return attiny13a_reset_input_next_deadline(&r); }
static int asserted(void) { return attiny13a_reset_input_asserted(&r); }

int initial_release(void) {
 CHECK(init(5000000,5000000));CHECK(!asserted()&&!r.raw_low&&!r.qualified&&!r.fault);
 CHECK(r.phase==AT13_RESET_INPUT_IDLE&&next()==AT13_RESET_INPUT_NEVER);
 CHECK(advance(UINT64_C(1000000000000))&&!asserted()&&next()==AT13_RESET_INPUT_NEVER);
 CHECK(attiny13a_reset_input_take_changes(&r)==0);return 0;
}
int separate_qualification_and_propagation(void) {
 CHECK(init(5000000,5000000));CHECK(set(10,0,5000000));
 CHECK(!asserted()&&r.raw_low&&r.phase==AT13_RESET_INPUT_QUALIFY&&next()==110);
 CHECK(advance(109)&&!asserted()&&!r.qualified&&next()==110);
 CHECK(advance(110)&&r.qualified&&!asserted()&&r.phase==AT13_RESET_INPUT_PROPAGATE&&next()==140);
 CHECK(r.qualified_at_ps==110&&advance(139)&&!asserted());
 CHECK(advance(140)&&asserted()&&r.last_change_ps==140&&next()==AT13_RESET_INPUT_NEVER);
 CHECK(attiny13a_reset_input_take_changes(&r)==AT13_RESET_INPUT_ASSERT);
 CHECK(set(150,2500000,5000000)&&asserted()&&!r.raw_low&&next()==350);
 CHECK(advance(350)&&asserted()&&!r.qualified&&next()==390);
 CHECK(advance(389)&&asserted());CHECK(advance(390)&&!asserted()&&r.last_change_ps==390);
 CHECK(attiny13a_reset_input_take_changes(&r)==AT13_RESET_INPUT_RELEASE);
 CHECK(attiny13a_reset_input_take_changes(&r)==0);return 0;
}
int short_low_cancels_qualification(void) {
 CHECK(init(5000000,5000000)&&set(10,0,5000000));
 CHECK(set(109,5000000,5000000)&&next()==AT13_RESET_INPUT_NEVER);
 CHECK(advance(10000)&&!asserted()&&!r.qualified&&!r.raw_low);
 CHECK(attiny13a_reset_input_take_changes(&r)==0);return 0;
}
int opposite_edge_cancels_assertion_propagation(void) {
 CHECK(init(0,5000000)&&advance(100));CHECK(r.qualified&&!asserted()&&next()==130);
 CHECK(set(120,5000000,5000000)&&!r.qualified&&next()==AT13_RESET_INPUT_NEVER);
 CHECK(advance(10000)&&!asserted()&&attiny13a_reset_input_take_changes(&r)==0);return 0;
}
int short_high_cancels_release_qualification(void) {
 CHECK(init(0,5000000)&&advance(130)&&asserted());
 CHECK(attiny13a_reset_input_take_changes(&r)==AT13_RESET_INPUT_ASSERT);
 CHECK(set(200,5000000,5000000)&&next()==400);
 CHECK(set(399,0,5000000)&&asserted()&&next()==AT13_RESET_INPUT_NEVER);
 CHECK(advance(10000)&&asserted()&&attiny13a_reset_input_take_changes(&r)==0);return 0;
}
int opposite_edge_cancels_release_propagation(void) {
 CHECK(init(0,5000000)&&advance(130)&&asserted());
 CHECK(attiny13a_reset_input_take_changes(&r)==AT13_RESET_INPUT_ASSERT);
 CHECK(set(200,5000000,5000000)&&advance(400));
 CHECK(asserted()&&!r.qualified&&r.phase==AT13_RESET_INPUT_PROPAGATE&&next()==440);
 CHECK(set(410,0,5000000)&&r.qualified&&next()==AT13_RESET_INPUT_NEVER);
 CHECK(advance(10000)&&asserted()&&attiny13a_reset_input_take_changes(&r)==0);return 0;
}
int hysteresis_keeps_both_candidate_polarities(void) {
 CHECK(init(5000000,5000000)&&set(10,1500000,5000000));
 CHECK(set(50,2000000,5000000)&&r.raw_low&&next()==110);
 CHECK(advance(140)&&asserted());
 CHECK(set(150,2500000,5000000)&&!r.raw_low&&next()==350);
 CHECK(set(200,2000000,5000000)&&!r.raw_low&&next()==350);
 CHECK(advance(390)&&!asserted());
 CHECK(attiny13a_reset_input_take_changes(&r)==(AT13_RESET_INPUT_ASSERT|AT13_RESET_INPUT_RELEASE));return 0;
}
int initial_band_is_released(void) {
 CHECK(init(2000000,5000000)&&!r.raw_low&&!asserted()&&next()==AT13_RESET_INPUT_NEVER);
 CHECK(set(10,1500000,5000000)&&r.raw_low&&next()==110);return 0;
}
int fractional_thresholds_are_not_rounded(void) {
 attiny13a_reset_input_profile_t tiny={333333,666667,0,0,0,0};
 CHECK(attiny13a_reset_input_init(&r,&tiny,0,1,3));
 CHECK(!r.raw_low&&!asserted()); //1uV >0.999999uV, not below a rounded threshold.
 CHECK(set(1,0,3)&&asserted());
 CHECK(set(2,2,3)&&asserted()); //2uV <2.000001uV, still inside the hysteresis band.
 CHECK(set(3,3,3)&&!asserted());return 0;
}
int signed32_extremes_do_not_overflow(void) {
 attiny13a_reset_input_profile_t fast={300000,500000,0,0,0,0};
 CHECK(attiny13a_reset_input_init(&r,&fast,0,INT32_MAX,INT32_MAX)&&!asserted());
 CHECK(set(1,INT32_MIN,INT32_MAX)&&asserted());
 CHECK(set(2,INT32_MAX,INT32_MAX)&&!asserted());return 0;
}
int vcc_changes_reevaluate_fixed_pin_voltage(void) {
 CHECK(init(1400000,3000000)&&!asserted());
 CHECK(set(10,1400000,5000000)&&r.raw_low&&next()==110);
 CHECK(advance(140)&&asserted());
 CHECK(set(150,1400000,2000000)&&!r.raw_low&&next()==350);
 CHECK(advance(390)&&!asserted());return 0;
}
int atomic_common_mode_changes_do_not_invent_pulses(void) {
 CHECK(init(5000000,5000000));
 CHECK(set(10,1800000,1800000)&&set(20,3000000,3000000));
 CHECK(set(30,0,0)&&!asserted()&&!r.raw_low&&next()==AT13_RESET_INPUT_NEVER);
 CHECK(set(40,5000000,5000000)&&advance(10000)&&!asserted());
 CHECK(attiny13a_reset_input_take_changes(&r)==0);return 0;
}
int vcc_zero_cancels_candidate_and_releases(void) {
 CHECK(init(0,5000000)&&advance(100)&&next()==130);
 CHECK(set(110,0,0)&&!asserted()&&next()==AT13_RESET_INPUT_NEVER);
 CHECK(advance(10000)&&!asserted());
 CHECK(set(10010,0,5000000)&&next()==10110&&advance(10140)&&asserted());
 CHECK(attiny13a_reset_input_take_changes(&r)==AT13_RESET_INPUT_ASSERT);
 CHECK(set(10150,0,0)&&!asserted()&&r.last_change_ps==10150);
 CHECK(attiny13a_reset_input_take_changes(&r)==AT13_RESET_INPUT_RELEASE);
 CHECK(set(10200,0,5000000)&&next()==10300&&advance(10330)&&asserted());return 0;
}
int zero_durations_and_equal_time_order(void) {
 attiny13a_reset_input_profile_t fast={300000,500000,0,0,10,0};
 CHECK(attiny13a_reset_input_init(&r,&fast,5,0,5000000)&&!asserted()&&next()==15);
 // Caller observes the due assertion before applying the equal-time input.
 CHECK(advance(15)&&asserted()&&r.last_change_ps==15);
 CHECK(set(15,5000000,5000000)&&!asserted()&&r.last_change_ps==15);
 CHECK(attiny13a_reset_input_take_changes(&r)==(AT13_RESET_INPUT_ASSERT|AT13_RESET_INPUT_RELEASE));
 fast.assert_propagation_ps=0;
 CHECK(attiny13a_reset_input_init(&r,&fast,0,0,5000000)&&asserted()&&next()==AT13_RESET_INPUT_NEVER);
 CHECK(attiny13a_reset_input_take_changes(&r)==AT13_RESET_INPUT_ASSERT);return 0;
}
int deadline_precedes_equal_time_voltage(void) {
 CHECK(init(0,5000000));CHECK(set(130,5000000,5000000));
 CHECK(asserted()&&r.last_change_ps==130&&next()==330);
 CHECK(advance(370)&&!asserted());return 0;
}
int repeated_same_voltage_preserves_deadline(void) {
 CHECK(init(0,5000000)&&set(50,0,5000000)&&next()==100);
 CHECK(advance(100)&&set(110,0,5000000)&&next()==130);
 CHECK(advance(130)&&asserted());return 0;
}
int invalid_profiles(void) {
 const attiny13a_reset_input_profile_t invalid[]={
  {199999,500000,0,0,0,0},{300000,900001,0,0,0,0},
  {500000,500000,0,0,0,0},{600000,500000,0,0,0,0},
  {300000,500000,UINT64_MAX,0,0,0},{300000,500000,0,UINT64_MAX,0,0},
  {300000,500000,UINT64_MAX-5,0,5,0},{300000,500000,0,UINT64_MAX-5,0,5}
 };
 for(unsigned i=0;i<sizeof invalid/sizeof invalid[0];i++) {
  CHECK(!attiny13a_reset_input_init(&r,&invalid[i],0,5000000,5000000));
  CHECK((r.fault&AT13_RESET_INPUT_BAD_PROFILE)&&!asserted()&&next()==AT13_RESET_INPUT_NEVER);
 }
 CHECK(!attiny13a_reset_input_init(&r,NULL,0,0,5000000)&&(r.fault&AT13_RESET_INPUT_BAD_PROFILE));
 CHECK(!attiny13a_reset_input_init(NULL,&profile,0,0,5000000));return 0;
}
int faults_are_sticky_and_freeze_output(void) {
 CHECK(init(0,5000000)&&advance(130)&&asserted());
 CHECK(!set(140,5000000,-1)&&(r.fault&AT13_RESET_INPUT_BAD_INPUT));
 CHECK(asserted()&&r.now_ps==130&&r.reset_uv==0&&next()==AT13_RESET_INPUT_NEVER);
 CHECK(!advance(10000)&&asserted());CHECK(init(5000000,5000000)&&!r.fault&&!asserted());
 CHECK(advance(10)&&!advance(9)&&(r.fault&AT13_RESET_INPUT_BAD_TIME)&&r.now_ps==10);
 CHECK(!set(11,0,5000000)&&!asserted());
 CHECK(init(0,5000000)&&!advance(UINT64_MAX)&&(r.fault&AT13_RESET_INPUT_BAD_TIME));
 CHECK(!attiny13a_reset_input_init(&r,&profile,UINT64_MAX,0,5000000)&&(r.fault&AT13_RESET_INPUT_BAD_TIME));
 return 0;
}
int deadline_overflow_is_detected_in_both_stages(void) {
 CHECK(!attiny13a_reset_input_init(&r,&profile,UINT64_MAX-5,0,5000000));
 CHECK((r.fault&AT13_RESET_INPUT_TIME_OVERFLOW)&&!asserted()&&next()==AT13_RESET_INPUT_NEVER);
 CHECK(attiny13a_reset_input_init(&r,&profile,UINT64_MAX-120,0,5000000));
 CHECK(next()==UINT64_MAX-20);
 CHECK(!advance(UINT64_MAX-20)&&(r.fault&AT13_RESET_INPUT_TIME_OVERFLOW)&&!asserted());
 CHECK(next()==AT13_RESET_INPUT_NEVER);return 0;
}
int large_stable_spans_are_event_bounded(void) {
 attiny13a_reset_input_profile_t huge={300000,500000,UINT64_MAX-1,0,0,0};
 CHECK(attiny13a_reset_input_init(&r,&huge,0,0,5000000)&&next()==UINT64_MAX-1);
 CHECK(advance(UINT64_MAX-2)&&!asserted());
 CHECK(advance(UINT64_MAX-1)&&asserted()&&r.last_change_ps==UINT64_MAX-1);
 CHECK(next()==AT13_RESET_INPUT_NEVER);return 0;
}
int independent_instances(void) {
 attiny13a_reset_input_t other;
 CHECK(init(0,5000000));CHECK(attiny13a_reset_input_init(&other,&profile,0,5000000,5000000));
 CHECK(advance(130)&&asserted());CHECK(!attiny13a_reset_input_asserted(&other));
 CHECK(other.now_ps==0&&other.fault==0&&attiny13a_reset_input_next_deadline(&other)==AT13_RESET_INPUT_NEVER);
 return 0;
}
int drives_existing_reset_aggregator_without_timeout(void) {
 power_reset_t power;power_reset_profile_t supply;power_reset_event_t event;
 power_reset_typical_profile(&supply,0,0,0);
 CHECK(power_reset_init(&power,&supply,0xff,0,5000000)&&!power.held);
 CHECK(init(0,5000000));
 CHECK(advance(next())&&!asserted()); // qualification alone never drives EXTRF.
 CHECK(power_reset_set_other_sources(&power,100,POWER_RESET_WDRF)&&power.held);
 CHECK(advance(next())&&asserted()&&r.now_ps==130);
 CHECK(power_reset_set_other_sources(&power,130,POWER_RESET_WDRF|POWER_RESET_EXTRF)&&power.held);
 CHECK(power_reset_set_other_sources(&power,200,POWER_RESET_EXTRF)&&power.held);
 CHECK(set(300,5000000,5000000));CHECK(advance(next())&&asserted());
 CHECK(advance(next())&&!asserted()&&r.now_ps==540);
 CHECK((power.causes&(POWER_RESET_WDRF|POWER_RESET_EXTRF))==(POWER_RESET_WDRF|POWER_RESET_EXTRF));
 CHECK(power_reset_set_other_sources(&power,540,0)&&!power.held);
 unsigned released=0;
 while(power_reset_pop_event(&power,&event))if(event.kind==POWER_RESET_RELEASE&&event.at==540) {
  CHECK((event.causes&(POWER_RESET_WDRF|POWER_RESET_EXTRF))==(POWER_RESET_WDRF|POWER_RESET_EXTRF));released++;
 }
 CHECK(released==1);
 CHECK(power_reset_next_deadline(&power)==POWER_RESET_NEVER);return 0;
}
`);

const cases={
  initial_release:'an undriven RESET at VCC starts released and has no periodic work',
  separate_qualification_and_propagation:'assertion and release each expose qualification and propagation deadlines',
  short_low_cancels_qualification:'a short low pulse cancels before qualification',
  opposite_edge_cancels_assertion_propagation:'a returning high cancels the chosen inertial assertion stage',
  short_high_cancels_release_qualification:'a short high pulse preserves an asserted output',
  opposite_edge_cancels_release_propagation:'a returning low cancels the inertial release stage',
  hysteresis_keeps_both_candidate_polarities:'motion inside hysteresis preserves each candidate and its deadline',
  initial_band_is_released:'initial voltage inside the band starts from a declared released state',
  fractional_thresholds_are_not_rounded:'threshold cross-products retain sub-microvolt fractions',
  signed32_extremes_do_not_overflow:'signed32 voltage extrema remain arithmetically safe',
  vcc_changes_reevaluate_fixed_pin_voltage:'VCC changes can assert and release an unchanged RESET voltage',
  atomic_common_mode_changes_do_not_invent_pulses:'atomic pull-up/VCC changes create no fictitious pulses',
  vcc_zero_cancels_candidate_and_releases:'VCC0 leaves POR ownership and positive supply starts fresh qualification',
  zero_durations_and_equal_time_order:'zero delays terminate and equal-time outputs remain observable',
  deadline_precedes_equal_time_voltage:'a due deadline precedes an equal-time voltage change',
  repeated_same_voltage_preserves_deadline:'repeated levels do not restart an existing stage',
  invalid_profiles:'invalid threshold/timing profiles latch explicit faults',
  faults_are_sticky_and_freeze_output:'bad voltage/time freezes output until an explicit new init',
  deadline_overflow_is_detected_in_both_stages:'both qualification and propagation detect deadline overflow',
  large_stable_spans_are_event_bounded:'a near-uint64 stable span advances without per-tick work',
  independent_instances:'separate receiver instances share no mutable state',
  drives_existing_reset_aggregator_without_timeout:'qualified EXTRF holds aggregate reset alongside WDT without adding SUT',
};
for(const [name,description] of Object.entries(cases))test('ATtiny13A RESET receiver: '+description,()=>{
  const line=make()[name]();
  assert.equal(line,0,`${name}: inline C assertion failed at line ${line}`);
});
