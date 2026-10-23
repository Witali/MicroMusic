import {test} from 'node:test';
import assert from 'node:assert/strict';
import {compileAnalog} from './analog-test-build.mjs';

const make=compileAnalog('attiny13a-clki-periodic',[
  'web-player/native/devices/attiny13a/clki_periodic.c',
  'web-player/native/devices/attiny13a/clki_input.c',
],String.raw`
#include "../devices/attiny13a/clki_periodic.h"
#include <stddef.h>
#include <string.h>
#define CHECK(x) do{if(!(x))return __LINE__;}while(0)
static attiny13a_clki_periodic_t s,before;
static void snapshot(void){memcpy(&before,&s,sizeof s);}
static int unchanged(void){return !memcmp(&before,&s,sizeof s);}
static int take(uint64_t at,uint8_t level) {
 attiny13a_clki_edge_t edge; snapshot();
 CHECK(attiny13a_clki_periodic_peek(&s,&edge)==AT13_CLKI_PERIODIC_OK&&unchanged());
 CHECK(edge.time_ps==at&&edge.level==level);
 CHECK(attiny13a_clki_periodic_peek(&s,&edge)==AT13_CLKI_PERIODIC_OK&&unchanged());
 CHECK(attiny13a_clki_periodic_consume(&s)==AT13_CLKI_PERIODIC_OK);
 CHECK(s.current_level==level&&s.next_level==!level);return 0;
}
int explicit_uneven_low_and_high_starts(void) {
 CHECK(attiny13a_clki_periodic_init(&s,0,0,3,5,5,30)==AT13_CLKI_PERIODIC_OK);
 const uint64_t low_start[]={5,8,13,16,21};
 for(unsigned i=0;i<5;i++)CHECK(!take(low_start[i],!(i&1)));
 CHECK(!s.remaining_edges&&s.next_time_ps==UINT64_MAX&&s.current_level==1&&s.horizon_ps==30);
 CHECK(attiny13a_clki_periodic_init(&s,0,1,3,5,4,16)==AT13_CLKI_PERIODIC_OK);
 const uint64_t high_start[]={3,8,11,16};
 for(unsigned i=0;i<4;i++)CHECK(!take(high_start[i],i&1));
 CHECK(!s.remaining_edges&&s.next_time_ps==UINT64_MAX&&s.current_level==1&&s.horizon_ps==16);
 return 0;
}
int zero_count_means_known_hold(void) {
 for(uint8_t level=0;level<2;level++) {
  CHECK(attiny13a_clki_periodic_init(&s,37,level,1,2,0,UINT64_MAX-1)==AT13_CLKI_PERIODIC_OK);
  CHECK(s.initial_level==level&&s.current_level==level&&s.next_level==!level);
  CHECK(s.next_time_ps==UINT64_MAX&&s.horizon_ps==UINT64_MAX-1&&!s.remaining_edges);
  attiny13a_clki_edge_t out={123,99};snapshot();
  CHECK(attiny13a_clki_periodic_peek(&s,&out)==AT13_CLKI_PERIODIC_EMPTY&&unchanged());
  CHECK(out.time_ps==123&&out.level==99);
  CHECK(attiny13a_clki_periodic_consume(&s)==AT13_CLKI_PERIODIC_EMPTY&&unchanged());
 }
 return 0;
}
int exhausted_producer_does_not_extrapolate(void) {
 CHECK(attiny13a_clki_periodic_init(&s,10,0,9,7,1,UINT64_C(1000000000000000))==AT13_CLKI_PERIODIC_OK);
 CHECK(!take(17,1));snapshot();
 for(unsigned i=0;i<10;i++) {
  attiny13a_clki_edge_t out={999,99};
  CHECK(attiny13a_clki_periodic_peek(&s,&out)==AT13_CLKI_PERIODIC_EMPTY&&unchanged());
  CHECK(out.time_ps==999&&out.level==99);
  CHECK(attiny13a_clki_periodic_consume(&s)==AT13_CLKI_PERIODIC_EMPTY&&unchanged());
 }
 return 0;
}
int even_odd_counts_match_iterated_exact_streams(void) {
 const uint64_t high[]={1,7,33333},low[]={2,11,50000};
 for(unsigned variant=0;variant<3;variant++)for(uint8_t initial=0;initial<2;initial++)for(unsigned count=0;count<34;count++) {
  uint64_t final=37;uint8_t level=initial;
  for(unsigned i=0;i<count;i++){final+=level?high[variant]:low[variant];level^=1;}
  CHECK(attiny13a_clki_periodic_init(&s,37,initial,high[variant],low[variant],count,final+17)==AT13_CLKI_PERIODIC_OK);
  uint64_t at=37;level=initial;
  for(unsigned i=0;i<count;i++) {
   at+=level?high[variant]:low[variant];level^=1;
   CHECK(s.remaining_edges==count-i&&!take(at,level));
  }
  CHECK(at==final&&s.current_level==level&&!s.remaining_edges&&s.horizon_ps==final+17);
 }
 return 0;
}
int exact_large_timestamps_and_last_legal_endpoint(void) {
 const uint64_t start=(UINT64_C(1)<<53)+37;
 CHECK(attiny13a_clki_periodic_init(&s,start,0,50000,20000,4,start+140000)==AT13_CLKI_PERIODIC_OK);
 CHECK(!take(start+20000,1)&&!take(start+70000,0));
 CHECK(!take(start+90000,1)&&!take(start+140000,0));
 CHECK(attiny13a_clki_periodic_init(&s,UINT64_MAX-2,0,1,1,1,UINT64_MAX-1)==AT13_CLKI_PERIODIC_OK);
 CHECK(!take(UINT64_MAX-1,1)&&s.next_time_ps==UINT64_MAX&&!s.remaining_edges);
 CHECK(attiny13a_clki_periodic_init(&s,UINT64_MAX-1,1,1,1,0,UINT64_MAX-1)==AT13_CLKI_PERIODIC_OK);
 return 0;
}
int unused_tail_duration_cannot_overflow_a_fictitious_edge(void) {
 CHECK(attiny13a_clki_periodic_init(&s,0,0,UINT64_MAX,1,1,1)==AT13_CLKI_PERIODIC_OK);
 CHECK(!take(1,1)&&!s.remaining_edges&&s.next_time_ps==UINT64_MAX);
 CHECK(attiny13a_clki_periodic_init(&s,0,1,1,UINT64_MAX,1,1)==AT13_CLKI_PERIODIC_OK);
 CHECK(!take(1,0)&&!s.remaining_edges&&s.next_time_ps==UINT64_MAX);
 CHECK(attiny13a_clki_periodic_init(&s,0,0,UINT64_MAX,UINT64_MAX,0,100)==AT13_CLKI_PERIODIC_OK);
 CHECK(!s.remaining_edges&&s.next_time_ps==UINT64_MAX&&s.current_level==0);
 return 0;
}
int products_and_final_time_are_checked_before_acceptance(void) {
 CHECK(attiny13a_clki_periodic_init(&s,0,0,1,1,UINT64_MAX-1,UINT64_MAX-1)==AT13_CLKI_PERIODIC_OK);
 CHECK(s.remaining_edges==UINT64_MAX-1&&!take(1,1));
 CHECK(s.remaining_edges==UINT64_MAX-2&&s.next_time_ps==2);snapshot();
 CHECK(attiny13a_clki_periodic_init(&s,0,0,1,1,UINT64_MAX,UINT64_MAX-1)==AT13_CLKI_PERIODIC_BAD_TIME&&unchanged());
 CHECK(attiny13a_clki_periodic_init(&s,UINT64_MAX-2,0,1,1,2,UINT64_MAX-1)==AT13_CLKI_PERIODIC_BAD_TIME&&unchanged());
 CHECK(attiny13a_clki_periodic_init(&s,0,0,UINT64_MAX,1,2,UINT64_MAX-1)==AT13_CLKI_PERIODIC_BAD_TIME&&unchanged());
 CHECK(attiny13a_clki_periodic_init(&s,0,1,UINT64_MAX/2+1,1,4,UINT64_MAX-1)==AT13_CLKI_PERIODIC_BAD_TIME&&unchanged());
 const uint64_t half=(UINT64_MAX-1)/2;
 CHECK(attiny13a_clki_periodic_init(&s,0,0,half,half,2,UINT64_MAX-1)==AT13_CLKI_PERIODIC_OK);
 CHECK(!take(half,1)&&!take(UINT64_MAX-1,0));
 return 0;
}
int malformed_init_is_atomic(void) {
 CHECK(attiny13a_clki_periodic_init(&s,10,0,3,5,3,30)==AT13_CLKI_PERIODIC_OK);snapshot();
 CHECK(attiny13a_clki_periodic_init(&s,10,2,3,5,3,30)==AT13_CLKI_PERIODIC_BAD_ARGUMENT&&unchanged());
 CHECK(attiny13a_clki_periodic_init(&s,10,0,0,5,3,30)==AT13_CLKI_PERIODIC_BAD_ARGUMENT&&unchanged());
 CHECK(attiny13a_clki_periodic_init(&s,10,0,3,0,3,30)==AT13_CLKI_PERIODIC_BAD_ARGUMENT&&unchanged());
 CHECK(attiny13a_clki_periodic_init(&s,UINT64_MAX,0,3,5,0,UINT64_MAX)==AT13_CLKI_PERIODIC_BAD_TIME&&unchanged());
 CHECK(attiny13a_clki_periodic_init(&s,10,0,3,5,0,9)==AT13_CLKI_PERIODIC_BAD_TIME&&unchanged());
 CHECK(attiny13a_clki_periodic_init(&s,10,0,3,5,3,22)==AT13_CLKI_PERIODIC_BAD_TIME&&unchanged());
 CHECK(attiny13a_clki_periodic_init(&s,10,0,3,5,3,UINT64_MAX)==AT13_CLKI_PERIODIC_BAD_TIME&&unchanged());
 CHECK(attiny13a_clki_periodic_init(NULL,0,0,1,1,0,0)==AT13_CLKI_PERIODIC_BAD_ARGUMENT);
 return 0;
}
int invalid_peek_and_alias_preserve_state_and_output(void) {
 CHECK(attiny13a_clki_periodic_init(&s,0,0,3,5,3,30)==AT13_CLKI_PERIODIC_OK);snapshot();
 CHECK(attiny13a_clki_periodic_peek(&s,NULL)==AT13_CLKI_PERIODIC_BAD_ARGUMENT&&unchanged());
 CHECK(attiny13a_clki_periodic_peek(&s,(attiny13a_clki_edge_t *)&s)==AT13_CLKI_PERIODIC_BAD_ARGUMENT&&unchanged());
 attiny13a_clki_edge_t out={99,99};attiny13a_clki_periodic_t empty={0};
 CHECK(attiny13a_clki_periodic_peek(NULL,&out)==AT13_CLKI_PERIODIC_BAD_ARGUMENT);
 CHECK(attiny13a_clki_periodic_peek(&empty,&out)==AT13_CLKI_PERIODIC_BAD_ARGUMENT&&out.time_ps==99&&out.level==99);
 CHECK(attiny13a_clki_periodic_consume(NULL)==AT13_CLKI_PERIODIC_BAD_ARGUMENT);
 CHECK(attiny13a_clki_periodic_consume(&empty)==AT13_CLKI_PERIODIC_BAD_ARGUMENT);
 CHECK(!take(5,1));return 0;
}
int lazy_refill_exceeds_bounded_queue_capacity(void) {
 attiny13a_clki_input_t q;attiny13a_clki_edge_t storage[8],edge;
 CHECK(attiny13a_clki_init(&q,storage,8,0,0)==AT13_CLKI_OK);
 CHECK(attiny13a_clki_periodic_init(&s,0,0,25000,25000,2000,100000000)==AT13_CLKI_PERIODIC_OK);
 uint64_t observed=0;unsigned full=0;
 while(s.remaining_edges||q.count) {
  while(s.remaining_edges&&q.count<8) {
   CHECK(attiny13a_clki_periodic_peek(&s,&edge)==AT13_CLKI_PERIODIC_OK);
   CHECK(attiny13a_clki_enqueue(&q,&edge,1,edge.time_ps)==AT13_CLKI_OK);
   CHECK(attiny13a_clki_periodic_consume(&s)==AT13_CLKI_PERIODIC_OK);
  }
  if(s.remaining_edges) {
   CHECK(attiny13a_clki_periodic_peek(&s,&edge)==AT13_CLKI_PERIODIC_OK);snapshot();
   CHECK(attiny13a_clki_enqueue(&q,&edge,1,edge.time_ps)==AT13_CLKI_BACKPRESSURE&&unchanged());full++;
  }
  CHECK(attiny13a_clki_consume(&q,&edge)==AT13_CLKI_OK);observed++;
  CHECK(edge.time_ps==observed*25000&&edge.level==(observed&1));
 }
 CHECK(observed==2000&&full>0&&q.now_ps==50000000&&s.current_level==0);
 CHECK(attiny13a_clki_enqueue(&q,NULL,0,s.horizon_ps)==AT13_CLKI_OK);
 CHECK(attiny13a_clki_hold_until(&q,100000000)==AT13_CLKI_OK);
 CHECK(s.next_time_ps==UINT64_MAX&&!s.remaining_edges);return 0;
}
int independent_producers_have_no_shared_cursor(void) {
 attiny13a_clki_periodic_t other;
 CHECK(attiny13a_clki_periodic_init(&s,0,0,3,5,3,30)==AT13_CLKI_PERIODIC_OK);
 CHECK(attiny13a_clki_periodic_init(&other,100,1,7,11,4,200)==AT13_CLKI_PERIODIC_OK);
 CHECK(!take(5,1));CHECK(other.next_time_ps==107&&other.remaining_edges==4&&other.current_level==1);
 CHECK(attiny13a_clki_periodic_consume(&other)==AT13_CLKI_PERIODIC_OK);
 CHECK(other.next_time_ps==118&&other.remaining_edges==3&&other.current_level==0);
 CHECK(s.next_time_ps==8&&s.remaining_edges==2&&s.current_level==1);return 0;
}
`);
const cases={
  explicit_uneven_low_and_high_starts:'both initial levels produce exact uneven high/low traces',
  zero_count_means_known_hold:'zero count is a finite known hold with no generated edge',
  exhausted_producer_does_not_extrapolate:'exhaustion does not extrapolate through the remaining horizon',
  even_odd_counts_match_iterated_exact_streams:'even/odd counts agree with explicit edge-by-edge streams',
  exact_large_timestamps_and_last_legal_endpoint:'timestamps above2^53 and MAX-1 remain exact',
  unused_tail_duration_cannot_overflow_a_fictitious_edge:'unused durations never manufacture an overflowing tail',
  products_and_final_time_are_checked_before_acceptance:'split products and final timestamp are checked atomically',
  malformed_init_is_atomic:'bad level/duration/time/horizon leaves initialized state unchanged',
  invalid_peek_and_alias_preserve_state_and_output:'invalid peek/output alias is atomic and recoverable',
  lazy_refill_exceeds_bounded_queue_capacity:'a2000-edge finite producer refills an eight-slot queue exactly',
  independent_producers_have_no_shared_cursor:'independent finite producers share no mutable cursor',
};
for(const [name,description] of Object.entries(cases))test('ATtiny13A CLKI periodic: '+description,()=>{
  const line=make()[name]();assert.equal(line,0,`${name}: C assertion at line ${line}`);
});
