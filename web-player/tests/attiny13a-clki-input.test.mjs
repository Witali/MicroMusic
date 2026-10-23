import {test} from 'node:test';
import assert from 'node:assert/strict';
import {compileAnalog} from './analog-test-build.mjs';

const make=compileAnalog('attiny13a-clki-input',[
  'web-player/native/devices/attiny13a/clki_input.c',
],String.raw`
#include "../devices/attiny13a/clki_input.h"
#include <stddef.h>
#include <string.h>
#define CHECK(expression) do { if(!(expression)) return __LINE__; } while(0)
static attiny13a_clki_input_t q;
static attiny13a_clki_edge_t storage[8];
typedef struct {attiny13a_clki_input_t q;attiny13a_clki_edge_t storage[8];} snapshot_t;
static snapshot_t before;
static int init(unsigned capacity,uint64_t time,uint8_t level) {
 memset(storage,0xa5,sizeof storage);
 return attiny13a_clki_init(&q,storage,capacity,time,level);
}
static void snapshot(void) {
 memcpy(&before.q,&q,sizeof q);memcpy(before.storage,storage,sizeof storage);
}
static int unchanged(void) {
 return !memcmp(&before.q,&q,sizeof q)&&!memcmp(before.storage,storage,sizeof storage);
}

int initial_levels_are_explicit(void) {
 for(uint8_t level=0;level<2;level++) {
  CHECK(init(8,37,level)==AT13_CLKI_OK);
  CHECK(attiny13a_clki_now(&q)==37&&attiny13a_clki_horizon(&q)==37);
  CHECK(attiny13a_clki_level(&q)==level&&attiny13a_clki_count(&q)==0);
  CHECK(attiny13a_clki_free(&q)==8);
  attiny13a_clki_edge_t out={999,99};snapshot();
  CHECK(attiny13a_clki_peek(&q,&out)==AT13_CLKI_EMPTY&&unchanged());
  CHECK(out.time_ps==999&&out.level==99);
  CHECK(attiny13a_clki_consume(&q,&out)==AT13_CLKI_EMPTY&&unchanged());
  CHECK(out.time_ps==999&&out.level==99);
 }
 return 0;
}
int unknown_is_not_a_clock_hold(void) {
 CHECK(init(8,10,0)==AT13_CLKI_OK);snapshot();
 CHECK(attiny13a_clki_hold_until(&q,11)==AT13_CLKI_UNKNOWN_HORIZON&&unchanged());
 CHECK(attiny13a_clki_enqueue(&q,NULL,0,100)==AT13_CLKI_OK);
 CHECK(attiny13a_clki_hold_until(&q,100)==AT13_CLKI_OK);
 CHECK(q.now_ps==100&&q.known_until_ps==100&&q.level==0&&!q.count);
 snapshot();CHECK(attiny13a_clki_hold_until(&q,101)==AT13_CLKI_UNKNOWN_HORIZON&&unchanged());
 return 0;
}
int long_high_and_low_holds_resume(void) {
 const uint64_t horizon=UINT64_C(1000000000000000);
 for(uint8_t level=0;level<2;level++) {
  CHECK(init(8,0,level)==AT13_CLKI_OK);
  CHECK(attiny13a_clki_enqueue(&q,NULL,0,horizon)==AT13_CLKI_OK);
  CHECK(attiny13a_clki_hold_until(&q,horizon)==AT13_CLKI_OK);
  CHECK(q.level==level&&!q.count);
  const attiny13a_clki_edge_t resume={horizon+37,(uint8_t)!level};
  CHECK(attiny13a_clki_enqueue(&q,&resume,1,horizon+100)==AT13_CLKI_OK);
  CHECK(attiny13a_clki_hold_until(&q,horizon+36)==AT13_CLKI_OK);
  snapshot();CHECK(attiny13a_clki_hold_until(&q,horizon+37)==AT13_CLKI_EDGE_PENDING&&unchanged());
  CHECK(attiny13a_clki_consume(&q,NULL)==AT13_CLKI_OK);
  CHECK(q.now_ps==horizon+37&&q.level==!level&&!q.count);
  CHECK(attiny13a_clki_hold_until(&q,horizon+100)==AT13_CLKI_OK);
 }
 return 0;
}
int peek_and_consume_preserve_exact_edges(void) {
 CHECK(init(8,0,0)==AT13_CLKI_OK);
 const attiny13a_clki_edge_t edges[]={{10,1},{25,0}};
 CHECK(attiny13a_clki_enqueue(&q,edges,2,40)==AT13_CLKI_OK);
 attiny13a_clki_edge_t out; snapshot();
 CHECK(attiny13a_clki_peek(&q,&out)==AT13_CLKI_OK&&unchanged());
 CHECK(out.time_ps==10&&out.level==1);
 CHECK(attiny13a_clki_consume(&q,&out)==AT13_CLKI_OK);
 CHECK(out.time_ps==10&&out.level==1&&q.now_ps==10&&q.level==1&&q.count==1);
 CHECK(attiny13a_clki_peek(&q,&out)==AT13_CLKI_OK&&out.time_ps==25&&out.level==0);
 CHECK(attiny13a_clki_consume(&q,&out)==AT13_CLKI_OK&&q.now_ps==25&&!q.level&&!q.count);
 CHECK(q.known_until_ps==40&&attiny13a_clki_hold_until(&q,40)==AT13_CLKI_OK);
 return 0;
}
int holds_cannot_skip_due_edges(void) {
 CHECK(init(8,0,0)==AT13_CLKI_OK);
 const attiny13a_clki_edge_t edges[]={{10,1},{25,0}};
 CHECK(attiny13a_clki_enqueue(&q,edges,2,40)==AT13_CLKI_OK);
 CHECK(attiny13a_clki_hold_until(&q,9)==AT13_CLKI_OK);snapshot();
 CHECK(attiny13a_clki_hold_until(&q,10)==AT13_CLKI_EDGE_PENDING&&unchanged());
 CHECK(attiny13a_clki_hold_until(&q,40)==AT13_CLKI_EDGE_PENDING&&unchanged());
 CHECK(attiny13a_clki_consume(&q,NULL)==AT13_CLKI_OK);
 CHECK(attiny13a_clki_hold_until(&q,24)==AT13_CLKI_OK);snapshot();
 CHECK(attiny13a_clki_hold_until(&q,25)==AT13_CLKI_EDGE_PENDING&&unchanged());
 CHECK(attiny13a_clki_consume(&q,NULL)==AT13_CLKI_OK);
 CHECK(attiny13a_clki_hold_until(&q,25)==AT13_CLKI_OK);
 CHECK(attiny13a_clki_hold_until(&q,40)==AT13_CLKI_OK);
 return 0;
}
int accepted_batch_owns_its_copy(void) {
 CHECK(init(8,0,0)==AT13_CLKI_OK);
 attiny13a_clki_edge_t edges[]={{10,1},{20,0}};
 CHECK(attiny13a_clki_enqueue(&q,edges,2,30)==AT13_CLKI_OK);
 edges[0]=(attiny13a_clki_edge_t){99,0};edges[1]=(attiny13a_clki_edge_t){100,1};
 attiny13a_clki_edge_t out;
 CHECK(attiny13a_clki_consume(&q,&out)==AT13_CLKI_OK&&out.time_ps==10&&out.level==1);
 CHECK(attiny13a_clki_consume(&q,&out)==AT13_CLKI_OK&&out.time_ps==20&&out.level==0);
 CHECK(q.known_until_ps==30);return 0;
}
int publication_is_atomic_and_monotonic(void) {
 CHECK(init(8,0,0)==AT13_CLKI_OK);
 const attiny13a_clki_edge_t first={10,1};
 CHECK(attiny13a_clki_enqueue(&q,&first,1,20)==AT13_CLKI_OK);snapshot();
 CHECK(attiny13a_clki_enqueue(&q,NULL,0,19)==AT13_CLKI_BAD_TIME&&unchanged());
 const attiny13a_clki_edge_t beyond[]={{21,0},{40,1}};
 CHECK(attiny13a_clki_enqueue(&q,beyond,2,39)==AT13_CLKI_BAD_TIME&&unchanged());
 const attiny13a_clki_edge_t revised={20,0};
 CHECK(attiny13a_clki_enqueue(&q,&revised,1,40)==AT13_CLKI_BAD_TIME&&unchanged());
 const attiny13a_clki_edge_t inside_published_hold={15,0};
 CHECK(attiny13a_clki_enqueue(&q,&inside_published_hold,1,40)==AT13_CLKI_BAD_TIME&&unchanged());
 CHECK(attiny13a_clki_enqueue(&q,NULL,0,20)==AT13_CLKI_OK&&unchanged());
 CHECK(attiny13a_clki_enqueue(&q,beyond,2,40)==AT13_CLKI_OK);
 CHECK(q.count==3&&q.known_until_ps==40&&q.now_ps==0&&q.level==0);
 return 0;
}
int malformed_times_do_not_partially_load(void) {
 CHECK(init(8,5,0)==AT13_CLKI_OK);snapshot();
 const attiny13a_clki_edge_t invalid[][2]={
  {{5,1},{10,0}},{{4,1},{10,0}},{{10,1},{10,0}},{{11,1},{10,0}},
  {{10,1},{AT13_CLKI_NEVER,0}}
 };
 for(unsigned i=0;i<sizeof invalid/sizeof invalid[0];i++) {
  CHECK(attiny13a_clki_enqueue(&q,invalid[i],2,100)==AT13_CLKI_BAD_TIME&&unchanged());
 }
 const attiny13a_clki_edge_t good[]={{10,1},{11,0}};
 CHECK(attiny13a_clki_enqueue(&q,good,2,11)==AT13_CLKI_OK);
 CHECK(attiny13a_clki_consume(&q,NULL)==AT13_CLKI_OK);
 CHECK(attiny13a_clki_consume(&q,NULL)==AT13_CLKI_OK);snapshot();
 CHECK(attiny13a_clki_hold_until(&q,10)==AT13_CLKI_BAD_TIME&&unchanged());
 CHECK(attiny13a_clki_hold_until(&q,AT13_CLKI_NEVER)==AT13_CLKI_BAD_TIME&&unchanged());
 CHECK(attiny13a_clki_enqueue(&q,NULL,0,AT13_CLKI_NEVER)==AT13_CLKI_BAD_TIME&&unchanged());
 return 0;
}
int repeated_levels_do_not_partially_load(void) {
 CHECK(init(8,0,0)==AT13_CLKI_OK);snapshot();
 const attiny13a_clki_edge_t repeated[]={{10,1},{20,1}};
 CHECK(attiny13a_clki_enqueue(&q,repeated,2,30)==AT13_CLKI_BAD_LEVEL&&unchanged());
 const attiny13a_clki_edge_t bad_first={10,0},bad_value={10,2},good_first={10,1};
 CHECK(attiny13a_clki_enqueue(&q,&bad_first,1,30)==AT13_CLKI_BAD_LEVEL&&unchanged());
 CHECK(attiny13a_clki_enqueue(&q,&bad_value,1,30)==AT13_CLKI_BAD_LEVEL&&unchanged());
 CHECK(attiny13a_clki_enqueue(&q,&good_first,1,10)==AT13_CLKI_OK);snapshot();
 const attiny13a_clki_edge_t repeat_tail={11,1};
 CHECK(attiny13a_clki_enqueue(&q,&repeat_tail,1,20)==AT13_CLKI_BAD_LEVEL&&unchanged());
 CHECK(attiny13a_clki_consume(&q,NULL)==AT13_CLKI_OK);snapshot();
 CHECK(attiny13a_clki_enqueue(&q,&repeat_tail,1,20)==AT13_CLKI_BAD_LEVEL&&unchanged());
 const attiny13a_clki_edge_t opposite={11,0};
 CHECK(attiny13a_clki_enqueue(&q,&opposite,1,20)==AT13_CLKI_OK);
 return 0;
}
int full_queue_backpressure_is_atomic(void) {
 CHECK(init(2,0,0)==AT13_CLKI_OK);
 const attiny13a_clki_edge_t first[]={{10,1},{20,0}},second[]={{30,1},{40,0}};
 CHECK(attiny13a_clki_enqueue(&q,first,2,20)==AT13_CLKI_OK);snapshot();
 CHECK(attiny13a_clki_enqueue(&q,second,2,40)==AT13_CLKI_BACKPRESSURE&&unchanged());
 CHECK(attiny13a_clki_enqueue(&q,NULL,0,25)==AT13_CLKI_OK);
 CHECK(attiny13a_clki_consume(&q,NULL)==AT13_CLKI_OK);snapshot();
 CHECK(attiny13a_clki_enqueue(&q,second,2,40)==AT13_CLKI_BACKPRESSURE&&unchanged());
 CHECK(attiny13a_clki_consume(&q,NULL)==AT13_CLKI_OK);
 CHECK(attiny13a_clki_enqueue(&q,second,2,40)==AT13_CLKI_OK);
 CHECK(q.count==2&&q.known_until_ps==40&&q.now_ps==20);
 return 0;
}
int ring_wrap_keeps_order(void) {
 CHECK(init(4,0,0)==AT13_CLKI_OK);
 const attiny13a_clki_edge_t first[]={{10,1},{20,0},{30,1}};
 const attiny13a_clki_edge_t second[]={{40,0},{50,1},{60,0}};
 CHECK(attiny13a_clki_enqueue(&q,first,3,30)==AT13_CLKI_OK);
 CHECK(attiny13a_clki_consume(&q,NULL)==AT13_CLKI_OK&&attiny13a_clki_consume(&q,NULL)==AT13_CLKI_OK);
 CHECK(attiny13a_clki_enqueue(&q,second,3,60)==AT13_CLKI_OK&&q.count==4);
 for(unsigned i=0;i<4;i++) {
  attiny13a_clki_edge_t out;
  CHECK(attiny13a_clki_consume(&q,&out)==AT13_CLKI_OK);
  CHECK(out.time_ps==30+i*10&&out.level==!(i&1));
 }
 CHECK(q.now_ps==60&&q.level==0&&!q.count&&attiny13a_clki_free(&q)==4);
 return 0;
}
int batch_partitions_produce_identical_streams(void) {
 attiny13a_clki_edge_t edges[7];
 for(unsigned i=0;i<7;i++)edges[i]=(attiny13a_clki_edge_t){17*(i*i+1),(uint8_t)!(i&1)};
 for(unsigned partition=0;partition<64;partition++) {
  CHECK(init(8,0,0)==AT13_CLKI_OK);unsigned begin=0,observed=0;
  for(unsigned end=1;end<=7;end++)if(end==7||(partition&(1u<<(end-1)))) {
   CHECK(attiny13a_clki_enqueue(&q,edges+begin,end-begin,edges[end-1].time_ps)==AT13_CLKI_OK);
   while(q.count) {
    attiny13a_clki_edge_t out;CHECK(attiny13a_clki_consume(&q,&out)==AT13_CLKI_OK);
    CHECK(out.time_ps==edges[observed].time_ps&&out.level==edges[observed].level);observed++;
   }
   begin=end;
  }
  CHECK(observed==7&&q.now_ps==edges[6].time_ps&&q.level==1);
  CHECK(attiny13a_clki_enqueue(&q,NULL,0,1000)==AT13_CLKI_OK);
  CHECK(attiny13a_clki_hold_until(&q,1000)==AT13_CLKI_OK&&q.now_ps==1000&&!q.count);
 }
 return 0;
}
int single_slot_stream_has_no_extrapolation(void) {
 CHECK(init(1,0,0)==AT13_CLKI_OK);
 for(unsigned i=1;i<20;i++) {
  const attiny13a_clki_edge_t next={i*i*100,(uint8_t)(i&1)};
  CHECK(attiny13a_clki_enqueue(&q,&next,1,next.time_ps)==AT13_CLKI_OK);
  CHECK(attiny13a_clki_consume(&q,NULL)==AT13_CLKI_OK&&q.now_ps==next.time_ps&&q.level==next.level);
  snapshot();CHECK(attiny13a_clki_hold_until(&q,next.time_ps+1)==AT13_CLKI_UNKNOWN_HORIZON&&unchanged());
 }
 return 0;
}
int full_uint64_precision_and_sentinel(void) {
 const uint64_t start=(UINT64_C(1)<<53)+37;
 CHECK(init(8,start,1)==AT13_CLKI_OK);
 const attiny13a_clki_edge_t edges[]={{start+1,0},{start+2,1},{UINT64_MAX-2,0}};
 CHECK(attiny13a_clki_enqueue(&q,edges,3,UINT64_MAX-1)==AT13_CLKI_OK);
 for(unsigned i=0;i<3;i++) {
  attiny13a_clki_edge_t out;CHECK(attiny13a_clki_consume(&q,&out)==AT13_CLKI_OK);
  CHECK(out.time_ps==edges[i].time_ps&&out.level==edges[i].level);
 }
 CHECK(attiny13a_clki_hold_until(&q,UINT64_MAX-1)==AT13_CLKI_OK);
 snapshot();const attiny13a_clki_edge_t bad={UINT64_MAX,1};
 CHECK(attiny13a_clki_enqueue(&q,&bad,1,UINT64_MAX-1)==AT13_CLKI_BAD_TIME&&unchanged());
 CHECK(attiny13a_clki_hold_until(&q,UINT64_MAX)==AT13_CLKI_BAD_TIME&&unchanged());
 return 0;
}
int invalid_arguments_preserve_initialized_state(void) {
 CHECK(init(8,0,0)==AT13_CLKI_OK);snapshot();
 CHECK(attiny13a_clki_init(NULL,storage,8,0,0)==AT13_CLKI_BAD_ARGUMENT&&unchanged());
 CHECK(attiny13a_clki_init(&q,NULL,8,0,0)==AT13_CLKI_BAD_ARGUMENT&&unchanged());
 CHECK(attiny13a_clki_init(&q,storage,0,0,0)==AT13_CLKI_BAD_ARGUMENT&&unchanged());
 CHECK(attiny13a_clki_init(&q,storage,UINT32_MAX,0,0)==AT13_CLKI_BAD_ARGUMENT&&unchanged());
 CHECK(attiny13a_clki_init(&q,storage,8,UINT64_MAX,0)==AT13_CLKI_BAD_TIME&&unchanged());
 CHECK(attiny13a_clki_init(&q,storage,8,0,2)==AT13_CLKI_BAD_LEVEL&&unchanged());
 CHECK(attiny13a_clki_enqueue(&q,NULL,1,10)==AT13_CLKI_BAD_ARGUMENT&&unchanged());
 CHECK(attiny13a_clki_peek(&q,NULL)==AT13_CLKI_BAD_ARGUMENT&&unchanged());
 attiny13a_clki_input_t empty={0};attiny13a_clki_edge_t out={99,99};
 CHECK(attiny13a_clki_enqueue(&empty,NULL,0,0)==AT13_CLKI_BAD_ARGUMENT);
 CHECK(attiny13a_clki_hold_until(NULL,0)==AT13_CLKI_BAD_ARGUMENT);
 CHECK(attiny13a_clki_consume(&empty,&out)==AT13_CLKI_BAD_ARGUMENT&&out.time_ps==99&&out.level==99);
 CHECK(attiny13a_clki_now(&empty)==AT13_CLKI_NEVER&&attiny13a_clki_horizon(NULL)==AT13_CLKI_NEVER);
 CHECK(attiny13a_clki_level(NULL)==255&&attiny13a_clki_count(&empty)==0&&attiny13a_clki_free(NULL)==0);
 return 0;
}
int aliasing_is_rejected_before_writes(void) {
 CHECK(init(8,0,0)==AT13_CLKI_OK);
 const attiny13a_clki_edge_t edge={10,1};CHECK(attiny13a_clki_enqueue(&q,&edge,1,10)==AT13_CLKI_OK);
 snapshot();CHECK(attiny13a_clki_enqueue(&q,storage,1,20)==AT13_CLKI_BAD_ARGUMENT&&unchanged());
 CHECK(attiny13a_clki_enqueue(&q,(const attiny13a_clki_edge_t *)&q,1,20)==AT13_CLKI_BAD_ARGUMENT&&unchanged());
 CHECK(attiny13a_clki_peek(&q,storage+1)==AT13_CLKI_BAD_ARGUMENT&&unchanged());
 CHECK(attiny13a_clki_consume(&q,storage+1)==AT13_CLKI_BAD_ARGUMENT&&unchanged());
 CHECK(attiny13a_clki_peek(&q,(attiny13a_clki_edge_t *)&q)==AT13_CLKI_BAD_ARGUMENT&&unchanged());
 CHECK(attiny13a_clki_consume(&q,(attiny13a_clki_edge_t *)&q)==AT13_CLKI_BAD_ARGUMENT&&unchanged());
 CHECK(attiny13a_clki_init(&q,(attiny13a_clki_edge_t *)&q,1,0,0)==AT13_CLKI_BAD_ARGUMENT&&unchanged());
 CHECK(attiny13a_clki_consume(&q,NULL)==AT13_CLKI_OK&&q.now_ps==10);
 return 0;
}
int independent_instances_keep_separate_horizons(void) {
 CHECK(init(8,0,0)==AT13_CLKI_OK);
 attiny13a_clki_input_t other;attiny13a_clki_edge_t other_storage[2];
 CHECK(attiny13a_clki_init(&other,other_storage,2,99,1)==AT13_CLKI_OK);
 CHECK(attiny13a_clki_enqueue(&q,NULL,0,1000)==AT13_CLKI_OK);
 const attiny13a_clki_edge_t edge={100,0};
 CHECK(attiny13a_clki_enqueue(&other,&edge,1,200)==AT13_CLKI_OK);
 CHECK(attiny13a_clki_hold_until(&q,1000)==AT13_CLKI_OK);
 CHECK(other.now_ps==99&&other.level==1&&other.count==1&&other.known_until_ps==200);
 CHECK(attiny13a_clki_consume(&other,NULL)==AT13_CLKI_OK&&other.now_ps==100&&!other.level);
 CHECK(q.now_ps==1000&&!q.level&&!q.count&&q.known_until_ps==1000);
 return 0;
}
`);

const cases={
  initial_levels_are_explicit:'initial time/level emits no edge and empty reads preserve outputs',
  unknown_is_not_a_clock_hold:'unknown future differs from a published edge-free hold',
  long_high_and_low_holds_resume:'high and low clock holds resume at exact supplied edges',
  peek_and_consume_preserve_exact_edges:'peek is nondestructive and consume updates time/level once',
  holds_cannot_skip_due_edges:'holds stop before an edge including an exact boundary',
  accepted_batch_owns_its_copy:'accepted edges do not alias the producer source array',
  publication_is_atomic_and_monotonic:'whole batches and their monotonic horizons publish atomically',
  malformed_times_do_not_partially_load:'reversed/repeated/past/sentinel times leave all bytes unchanged',
  repeated_levels_do_not_partially_load:'levels alternate within batches and across consumed/queued tails',
  full_queue_backpressure_is_atomic:'capacity backpressure accepts nothing and permits retry after draining',
  ring_wrap_keeps_order:'a wrapped full ring preserves the original order',
  batch_partitions_produce_identical_streams:'all64 partitions produce the same seven-edge stream',
  single_slot_stream_has_no_extrapolation:'single-slot reuse never infers a later edge from past periods',
  full_uint64_precision_and_sentinel:'timestamps above2^53 and through MAX-1 stay exact',
  invalid_arguments_preserve_initialized_state:'invalid arguments/init are recoverable and nonmutating',
  aliasing_is_rejected_before_writes:'input/output/state overlap is rejected before mutation',
  independent_instances_keep_separate_horizons:'independent queues share no mutable state',
};
for(const [name,description] of Object.entries(cases))test('ATtiny13A CLKI input: '+description,()=>{
  const line=make()[name]();
  assert.equal(line,0,`${name}: inline C assertion failed at line ${line}`);
});
