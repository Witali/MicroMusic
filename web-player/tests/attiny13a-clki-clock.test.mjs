import {test} from 'node:test';
import assert from 'node:assert/strict';
import {compileAnalog} from './analog-test-build.mjs';

const make=compileAnalog('attiny13a-clki-clock',[
  'web-player/native/devices/attiny13a/clki_clock.c',
  'web-player/native/devices/attiny13a/clki_input.c',
],String.raw`
#include "../devices/attiny13a/clki_clock.h"
#include "../devices/attiny13a/clki_input.h"
#include <stddef.h>
#include <string.h>
#define CHECK(expression) do { if(!(expression)) return __LINE__; } while(0)
#define EDGE(level,running,status,value) do { \
 uint8_t output=99;CHECK(attiny13a_clki_clock_edge(&s,level,running,&output)==status); \
 CHECK(output==((status)==AT13_CLKI_CLOCK_TRANSITION?(value):99)); \
} while(0)
static attiny13a_clki_clock_t s,before;
static void snapshot(void){memcpy(&before,&s,sizeof s);}
static int unchanged(void){return !memcmp(&before,&s,sizeof s);}

int initial_levels_and_divisors(void) {
 for(unsigned d=1;d<=256;d*=2)for(uint8_t input=0;input<2;input++) {
  CHECK(attiny13a_clki_clock_init(&s,input,d)==AT13_CLKI_CLOCK_OK);
  CHECK(s.divisor==d&&s.input_level==input&&s.output_level==(d==1?input:0));
  CHECK(!s.source_counter&&!s.pending_divisor&&!s.pending_wait_old_rise);
 }
 return 0;
}
int every_divisor_delivers_two_system_periods(void) {
 for(unsigned d=1;d<=256;d*=2) {
  CHECK(attiny13a_clki_clock_init(&s,0,d)==AT13_CLKI_CLOCK_OK);
  unsigned transitions=0,rises=0,falls=0;
  for(unsigned edge=0;edge<4*d;edge++) {
   uint8_t output=99,previous=s.output_level,level=!s.input_level;
   int status=attiny13a_clki_clock_edge(&s,level,1,&output);
   CHECK(status>=0);
   if(status==AT13_CLKI_CLOCK_TRANSITION) {
    CHECK(output!=previous&&output==s.output_level);transitions++;
    if(output)rises++;else falls++;
   } else CHECK(output==99&&s.output_level==previous);
   CHECK(s.source_counter<(d==1?1:d/2));
  }
  CHECK(transitions==4&&rises==2&&falls==2&&s.output_level==0&&!s.source_counter);
 }
 return 0;
}
int all81_switches_wait_old_then_new_period(void) {
 for(unsigned old=1;old<=256;old*=2)for(unsigned next=1;next<=256;next*=2) {
  CHECK(attiny13a_clki_clock_init(&s,0,old)==AT13_CLKI_CLOCK_OK);
  unsigned limit=0;
  while(!s.output_level) {
   uint8_t output=99;CHECK(++limit<=512);
   CHECK(attiny13a_clki_clock_edge(&s,!s.input_level,1,&output)>=0);
  }
  CHECK(s.input_level==1&&!s.source_counter);
  CHECK(attiny13a_clki_clock_request_divisor(&s,next)==AT13_CLKI_CLOCK_OK);
  CHECK(s.divisor==old&&s.output_level==1&&s.pending_divisor==next&&s.pending_wait_old_rise);
  unsigned source_rises=0,transitions=0;limit=0;
  for(;;) {
   uint8_t output=99,level=!s.input_level;if(level)source_rises++;
   int status=attiny13a_clki_clock_edge(&s,level,1,&output);CHECK(status>=0&&++limit<=1024);
   if(status) {
    transitions++;
    if(output)break;
    CHECK(s.divisor==old&&s.pending_divisor==next&&s.pending_wait_old_rise);
   } else CHECK(output==99&&s.divisor==old&&s.pending_divisor==next);
  }
  CHECK(source_rises==old&&transitions==2&&s.divisor==next&&s.output_level==1);
  CHECK(!s.source_counter&&!s.pending_divisor&&!s.pending_wait_old_rise);
  source_rises=0;transitions=0;limit=0;
  for(;;) {
   uint8_t output=99,level=!s.input_level;if(level)source_rises++;
   int status=attiny13a_clki_clock_edge(&s,level,1,&output);CHECK(status>=0&&++limit<=1024);
   if(status){transitions++;if(output)break;}else CHECK(output==99);
  }
  CHECK(source_rises==next&&transitions==2&&s.divisor==next&&!s.source_counter);
 }
 return 0;
}
int debug_request_after_fall_uses_next_old_rise(void) {
 CHECK(attiny13a_clki_clock_init(&s,0,4)==AT13_CLKI_CLOCK_OK);
 EDGE(1,1,AT13_CLKI_CLOCK_NONE,0);EDGE(0,1,AT13_CLKI_CLOCK_NONE,0);
 EDGE(1,1,AT13_CLKI_CLOCK_TRANSITION,1);EDGE(0,1,AT13_CLKI_CLOCK_NONE,0);
 EDGE(1,1,AT13_CLKI_CLOCK_NONE,0);EDGE(0,1,AT13_CLKI_CLOCK_NONE,0);
 EDGE(1,1,AT13_CLKI_CLOCK_TRANSITION,0);
 CHECK(attiny13a_clki_clock_request_divisor(&s,8)==AT13_CLKI_CLOCK_OK&&s.divisor==4&&!s.output_level);
 EDGE(0,1,AT13_CLKI_CLOCK_NONE,0);EDGE(1,1,AT13_CLKI_CLOCK_NONE,0);
 CHECK(s.divisor==4&&s.pending_divisor==8);
 EDGE(0,1,AT13_CLKI_CLOCK_NONE,0);EDGE(1,1,AT13_CLKI_CLOCK_TRANSITION,1);
 CHECK(s.divisor==8&&!s.pending_divisor&&!s.source_counter);
 return 0;
}
int last_valid_request_replaces_pending(void) {
 CHECK(attiny13a_clki_clock_init(&s,0,2)==AT13_CLKI_CLOCK_OK);
 CHECK(attiny13a_clki_clock_request_divisor(&s,4)==AT13_CLKI_CLOCK_OK);
 CHECK(attiny13a_clki_clock_request_divisor(&s,16)==AT13_CLKI_CLOCK_OK);
 CHECK(s.divisor==2&&s.pending_divisor==16&&s.output_level==0&&!s.source_counter);
 snapshot();CHECK(attiny13a_clki_clock_request_divisor(&s,3)==AT13_CLKI_CLOCK_BAD_ARGUMENT&&unchanged());
 EDGE(1,1,AT13_CLKI_CLOCK_TRANSITION,1);
 CHECK(s.divisor==16&&!s.pending_divisor&&!s.pending_wait_old_rise&&!s.source_counter);
 return 0;
}
int gating_freezes_partial_phase_and_request(void) {
 CHECK(attiny13a_clki_clock_init(&s,0,8)==AT13_CLKI_CLOCK_OK);
 for(unsigned i=0;i<3;i++) {EDGE(1,1,AT13_CLKI_CLOCK_NONE,0);EDGE(0,1,AT13_CLKI_CLOCK_NONE,0);}
 CHECK(s.source_counter==3&&s.output_level==0);
 CHECK(attiny13a_clki_clock_request_divisor(&s,4)==AT13_CLKI_CLOCK_OK);
 for(unsigned i=0;i<37;i++) {
  EDGE(1,0,AT13_CLKI_CLOCK_NONE,0);EDGE(0,0,AT13_CLKI_CLOCK_NONE,0);
  CHECK(s.source_counter==3&&s.divisor==8&&s.pending_divisor==4&&s.pending_wait_old_rise&&!s.output_level);
 }
 EDGE(1,1,AT13_CLKI_CLOCK_TRANSITION,1);
 CHECK(s.divisor==4&&!s.pending_divisor&&!s.source_counter);
 return 0;
}
int divide_one_gated_mismatch_has_no_fictitious_edge(void) {
 CHECK(attiny13a_clki_clock_init(&s,1,1)==AT13_CLKI_CLOCK_OK);
 EDGE(0,0,AT13_CLKI_CLOCK_NONE,0);CHECK(s.input_level==0&&s.output_level==1);
 EDGE(1,1,AT13_CLKI_CLOCK_NONE,0);CHECK(s.input_level==1&&s.output_level==1);
 EDGE(0,1,AT13_CLKI_CLOCK_TRANSITION,0);
 CHECK(attiny13a_clki_clock_init(&s,0,1)==AT13_CLKI_CLOCK_OK);
 EDGE(1,0,AT13_CLKI_CLOCK_NONE,0);CHECK(s.input_level==1&&s.output_level==0);
 EDGE(0,1,AT13_CLKI_CLOCK_NONE,0);EDGE(1,1,AT13_CLKI_CLOCK_TRANSITION,1);
 return 0;
}
int reset_preserves_levels_and_seeds_phase(void) {
 for(unsigned d=1;d<=256;d*=2) {
  CHECK(attiny13a_clki_clock_init(&s,0,2)==AT13_CLKI_CLOCK_OK);
  EDGE(1,1,AT13_CLKI_CLOCK_TRANSITION,1);EDGE(0,1,AT13_CLKI_CLOCK_NONE,0);
  CHECK(attiny13a_clki_clock_request_divisor(&s,32)==AT13_CLKI_CLOCK_OK);
  CHECK(attiny13a_clki_clock_reset_divisor(&s,d)==AT13_CLKI_CLOCK_OK);
  CHECK(s.divisor==d&&s.input_level==0&&s.output_level==1&&!s.source_counter);
  CHECK(!s.pending_divisor&&!s.pending_wait_old_rise);
  if(d==1) {EDGE(1,1,AT13_CLKI_CLOCK_NONE,0);EDGE(0,1,AT13_CLKI_CLOCK_TRANSITION,0);}
  else {
   for(unsigned i=1;i<=d/2;i++) {
    uint8_t output=99;int status=attiny13a_clki_clock_edge(&s,1,1,&output);
    CHECK(status==(i==d/2?AT13_CLKI_CLOCK_TRANSITION:AT13_CLKI_CLOCK_NONE));
    CHECK(output==(i==d/2?0:99));EDGE(0,1,AT13_CLKI_CLOCK_NONE,0);
   }
  }
 }
 CHECK(attiny13a_clki_clock_init(&s,1,4)==AT13_CLKI_CLOCK_OK);
 CHECK(attiny13a_clki_clock_reset_divisor(&s,1)==AT13_CLKI_CLOCK_OK);
 CHECK(s.input_level==1&&s.output_level==0);
 EDGE(0,1,AT13_CLKI_CLOCK_NONE,0);EDGE(1,1,AT13_CLKI_CLOCK_TRANSITION,1);
 return 0;
}
int uneven_source_phases_are_not_interpolated(void) {
 CHECK(attiny13a_clki_clock_init(&s,0,4)==AT13_CLKI_CLOCK_OK);
 const uint64_t timestamps[]={1,99,100,1000,1001,1002,UINT64_C(1000000000),UINT64_C(1000000001)};
 uint64_t observed[2]={0};unsigned count=0;
 for(unsigned i=0;i<8;i++) {
  uint8_t output=99;int status=attiny13a_clki_clock_edge(&s,!(i&1),1,&output);
  CHECK(status>=0);
  if(status){CHECK(count<2);observed[count++]=timestamps[i];}
 }
 CHECK(count==2&&observed[0]==100&&observed[1]==UINT64_C(1000000000));
 return 0;
}
int held_queue_composes_at_large_uint64_timestamps(void) {
 const uint64_t start=(UINT64_C(1)<<53)+37;
 attiny13a_clki_input_t q;attiny13a_clki_edge_t storage[4],edge;
 const attiny13a_clki_edge_t edges[]={{start+1,1},{start+1000,0},{UINT64_MAX-3,1},{UINT64_MAX-2,0}};
 CHECK(attiny13a_clki_init(&q,storage,4,start,0)==AT13_CLKI_OK);
 CHECK(attiny13a_clki_enqueue(&q,edges,4,UINT64_MAX-1)==AT13_CLKI_OK);
 CHECK(attiny13a_clki_clock_init(&s,0,1)==AT13_CLKI_CLOCK_OK);
 for(unsigned i=0;i<4;i++) {
  snapshot();CHECK(attiny13a_clki_peek(&q,&edge)==AT13_CLKI_OK);
  CHECK(attiny13a_clki_hold_until(&q,edge.time_ps-1)==AT13_CLKI_OK&&unchanged());
  CHECK(attiny13a_clki_consume(&q,&edge)==AT13_CLKI_OK&&edge.time_ps==edges[i].time_ps);
  EDGE(edge.level,1,AT13_CLKI_CLOCK_TRANSITION,edge.level);
 }
 snapshot();CHECK(attiny13a_clki_hold_until(&q,UINT64_MAX-1)==AT13_CLKI_OK&&unchanged());
 CHECK(q.now_ps==UINT64_MAX-1&&s.input_level==0&&s.output_level==0);
 return 0;
}
int invalid_arguments_are_atomic(void) {
 const uint32_t invalid[]={0,3,5,6,255,257,512,65536,65537,UINT32_MAX};
 CHECK(attiny13a_clki_clock_init(&s,0,8)==AT13_CLKI_CLOCK_OK);
 CHECK(attiny13a_clki_clock_request_divisor(&s,16)==AT13_CLKI_CLOCK_OK);snapshot();
 for(unsigned i=0;i<sizeof invalid/sizeof invalid[0];i++) {
  CHECK(attiny13a_clki_clock_init(&s,0,invalid[i])==AT13_CLKI_CLOCK_BAD_ARGUMENT&&unchanged());
  CHECK(attiny13a_clki_clock_request_divisor(&s,invalid[i])==AT13_CLKI_CLOCK_BAD_ARGUMENT&&unchanged());
  CHECK(attiny13a_clki_clock_reset_divisor(&s,invalid[i])==AT13_CLKI_CLOCK_BAD_ARGUMENT&&unchanged());
 }
 CHECK(attiny13a_clki_clock_init(&s,2,8)==AT13_CLKI_CLOCK_BAD_ARGUMENT&&unchanged());
 uint8_t output=99;
 CHECK(attiny13a_clki_clock_edge(&s,0,1,&output)==AT13_CLKI_CLOCK_BAD_ARGUMENT&&unchanged()&&output==99);
 CHECK(attiny13a_clki_clock_edge(&s,2,1,&output)==AT13_CLKI_CLOCK_BAD_ARGUMENT&&unchanged()&&output==99);
 CHECK(attiny13a_clki_clock_edge(&s,1,2,&output)==AT13_CLKI_CLOCK_BAD_ARGUMENT&&unchanged()&&output==99);
 CHECK(attiny13a_clki_clock_edge(&s,1,-1,&output)==AT13_CLKI_CLOCK_BAD_ARGUMENT&&unchanged()&&output==99);
 CHECK(attiny13a_clki_clock_edge(&s,1,1,NULL)==AT13_CLKI_CLOCK_BAD_ARGUMENT&&unchanged());
 CHECK(attiny13a_clki_clock_edge(&s,1,1,&s.output_level)==AT13_CLKI_CLOCK_BAD_ARGUMENT&&unchanged());
 CHECK(attiny13a_clki_clock_init(NULL,0,1)==AT13_CLKI_CLOCK_BAD_ARGUMENT);
 CHECK(attiny13a_clki_clock_request_divisor(NULL,1)==AT13_CLKI_CLOCK_BAD_ARGUMENT);
 CHECK(attiny13a_clki_clock_reset_divisor(NULL,1)==AT13_CLKI_CLOCK_BAD_ARGUMENT);
 CHECK(attiny13a_clki_clock_edge(NULL,1,1,&output)==AT13_CLKI_CLOCK_BAD_ARGUMENT&&output==99);
 attiny13a_clki_clock_t empty={0};
 CHECK(attiny13a_clki_clock_edge(&empty,1,1,&output)==AT13_CLKI_CLOCK_BAD_ARGUMENT&&output==99);
 EDGE(1,1,AT13_CLKI_CLOCK_NONE,0);CHECK(s.source_counter==1&&s.pending_divisor==16);
 return 0;
}
int separate_instances_do_not_share_phase(void) {
 attiny13a_clki_clock_t other;uint8_t output=99;
 CHECK(attiny13a_clki_clock_init(&s,0,2)==AT13_CLKI_CLOCK_OK);
 CHECK(attiny13a_clki_clock_init(&other,1,8)==AT13_CLKI_CLOCK_OK);
 EDGE(1,1,AT13_CLKI_CLOCK_TRANSITION,1);
 CHECK(other.input_level==1&&!other.output_level&&!other.source_counter&&other.divisor==8);
 CHECK(attiny13a_clki_clock_edge(&other,0,1,&output)==AT13_CLKI_CLOCK_NONE&&output==99);
 CHECK(attiny13a_clki_clock_edge(&other,1,1,&output)==AT13_CLKI_CLOCK_NONE&&output==99);
 CHECK(other.source_counter==1&&s.divisor==2&&s.input_level==1&&s.output_level==1&&!s.source_counter);
 return 0;
}
`);

const cases={
  initial_levels_and_divisors:'explicit initial levels and all nine divisors produce no fabricated edge',
  every_divisor_delivers_two_system_periods:'all divisors deliver the correct output periods with bounded phase',
  all81_switches_wait_old_then_new_period:'all81 divisor pairs retain the old period then establish the new period',
  debug_request_after_fall_uses_next_old_rise:'arbitrary debug-phase requests use the next actual old rising edge',
  last_valid_request_replaces_pending:'last valid request replaces pending without an immediate edge',
  gating_freezes_partial_phase_and_request:'gated source edges update input while phase/output/request stay frozen',
  divide_one_gated_mismatch_has_no_fictitious_edge:'divide-one resume ignores transitions already equal to held output',
  reset_preserves_levels_and_seeds_phase:'reset preserves both levels and seeds every divisor without an edge',
  uneven_source_phases_are_not_interpolated:'uneven source durations deliver transitions only on supplied edges',
  held_queue_composes_at_large_uint64_timestamps:'queue holds and resume compose above2^53 through MAX-1',
  invalid_arguments_are_atomic:'invalid arguments are nonsticky and preserve all state/output bytes',
  separate_instances_do_not_share_phase:'separate divider instances share no mutable state',
};
for(const [name,description] of Object.entries(cases))test('ATtiny13A CLKI clock: '+description,()=>{
  const line=make()[name]();
  assert.equal(line,0,`${name}: inline C assertion failed at line ${line}`);
});
