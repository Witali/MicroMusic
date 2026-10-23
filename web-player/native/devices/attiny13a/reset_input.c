#include "reset_input.h"

static int fail(attiny13a_reset_input_t *r,uint8_t fault) {
 r->fault|=fault;return 0;
}
static int profile_valid(const attiny13a_reset_input_profile_t *p) {
 return p&&p->assert_threshold_ppm>=200000&&p->release_threshold_ppm<=900000&&
  p->assert_threshold_ppm<p->release_threshold_ppm&&
  p->assert_qualification_ps<UINT64_MAX&&p->release_qualification_ps<UINT64_MAX&&
  p->assert_propagation_ps<UINT64_MAX-p->assert_qualification_ps&&
  p->release_propagation_ps<UINT64_MAX-p->release_qualification_ps;
}
static int after(attiny13a_reset_input_t *r,uint64_t delay,uint64_t *deadline) {
 if(delay>=UINT64_MAX-r->now_ps)return fail(r,AT13_RESET_INPUT_TIME_OVERFLOW);
 *deadline=r->now_ps+delay;return 1;
}
static void output(attiny13a_reset_input_t *r,uint8_t asserted) {
 if(r->asserted==asserted)return;
 r->asserted=asserted;r->last_change_ps=r->now_ps;
 r->changes|=asserted?AT13_RESET_INPUT_ASSERT:AT13_RESET_INPUT_RELEASE;
}
static void cancel(attiny13a_reset_input_t *r) {
 r->phase=AT13_RESET_INPUT_IDLE;r->deadline_ps=AT13_RESET_INPUT_NEVER;
 r->qualified=r->asserted;
}
static int evaluate(attiny13a_reset_input_t *r) {
 if(!r->vcc_uv) {
  cancel(r);r->raw_low=0;r->qualified=0;output(r,0);return 1;
 }
 /* Exact cross-products retain fractions below one microvolt and fit int64
  * for every signed32 uV input and every validated ppm threshold. */
 int64_t input=(int64_t)r->reset_uv*1000000;
 uint8_t raw=r->raw_low;
 if(input<=(int64_t)r->vcc_uv*r->profile.assert_threshold_ppm)raw=1;
 else if(input>=(int64_t)r->vcc_uv*r->profile.release_threshold_ppm)raw=0;
 if(raw!=r->raw_low) {
  r->raw_low=raw;cancel(r);
 }
 if(raw==r->asserted||r->phase!=AT13_RESET_INPUT_IDLE)return 1;
 uint64_t delay=raw?r->profile.assert_qualification_ps:r->profile.release_qualification_ps;
 if(!after(r,delay,&r->deadline_ps))return 0;
 r->phase=AT13_RESET_INPUT_QUALIFY;return 1;
}
int attiny13a_reset_input_advance(attiny13a_reset_input_t *r,uint64_t at) {
 if(!r||r->fault)return 0;
 if(at==AT13_RESET_INPUT_NEVER||at<r->now_ps)return fail(r,AT13_RESET_INPUT_BAD_TIME);
 while(r->phase!=AT13_RESET_INPUT_IDLE&&r->deadline_ps<=at) {
  r->now_ps=r->deadline_ps;
  if(r->phase==AT13_RESET_INPUT_QUALIFY) {
   uint64_t delay=r->raw_low?r->profile.assert_propagation_ps:r->profile.release_propagation_ps;
   uint64_t deadline;
   if(!after(r,delay,&deadline))return 0;
   r->qualified=r->raw_low;r->qualified_at_ps=r->now_ps;
   r->phase=AT13_RESET_INPUT_PROPAGATE;r->deadline_ps=deadline;
  } else {
   output(r,r->qualified);cancel(r);
  }
 }
 r->now_ps=at;return 1;
}
int attiny13a_reset_input_set_voltage(attiny13a_reset_input_t *r,
 uint64_t at,int32_t reset_uv,int32_t vcc_uv) {
 if(!r||r->fault)return 0;
 if(vcc_uv<0)return fail(r,AT13_RESET_INPUT_BAD_INPUT);
 if(!attiny13a_reset_input_advance(r,at))return 0;
 r->reset_uv=reset_uv;r->vcc_uv=vcc_uv;
 if(!evaluate(r))return 0;
 return attiny13a_reset_input_advance(r,at);
}
int attiny13a_reset_input_init(attiny13a_reset_input_t *r,
 const attiny13a_reset_input_profile_t *profile,uint64_t at,
 int32_t reset_uv,int32_t vcc_uv) {
 if(!r)return 0;
 *r=(attiny13a_reset_input_t){0};r->deadline_ps=AT13_RESET_INPUT_NEVER;
 if(!profile_valid(profile))return fail(r,AT13_RESET_INPUT_BAD_PROFILE);
 r->profile=*profile;r->now_ps=at;r->last_change_ps=at;r->qualified_at_ps=at;
 return attiny13a_reset_input_set_voltage(r,at,reset_uv,vcc_uv);
}
uint64_t attiny13a_reset_input_next_deadline(const attiny13a_reset_input_t *r) {
 return !r||r->fault?AT13_RESET_INPUT_NEVER:r->deadline_ps;
}
int attiny13a_reset_input_asserted(const attiny13a_reset_input_t *r) {
 return r&&r->asserted;
}
uint8_t attiny13a_reset_input_take_changes(attiny13a_reset_input_t *r) {
 if(!r)return 0;uint8_t changes=r->changes;r->changes=0;return changes;
}
