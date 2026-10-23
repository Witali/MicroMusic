#include "clki_input.h"
#include <stddef.h>

static int valid(const attiny13a_clki_input_t *q) {
 return q && q->storage && q->capacity;
}
static int overlaps(const void *a,size_t a_size,const void *b,size_t b_size) {
 uintptr_t x=(uintptr_t)a,y=(uintptr_t)b;
 return x<=y ? y-x<a_size : x-y<b_size;
}
static int aliases(const attiny13a_clki_input_t *q,const void *p,size_t size) {
 return overlaps(p,size,q,sizeof *q) ||
  overlaps(p,size,q->storage,(size_t)q->capacity*sizeof *q->storage);
}
static uint32_t index_at(const attiny13a_clki_input_t *q,uint32_t offset) {
 uint32_t until_end=q->capacity-q->head;
 return offset<until_end ? q->head+offset : offset-until_end;
}
static uint32_t successor(const attiny13a_clki_input_t *q,uint32_t index) {
 return index==q->capacity-1 ? 0 : index+1;
}
int attiny13a_clki_init(attiny13a_clki_input_t *q,
 attiny13a_clki_edge_t *storage,uint32_t capacity,uint64_t at,uint8_t level) {
 if(!q || !storage || !capacity || capacity>SIZE_MAX/sizeof *storage)
  return AT13_CLKI_BAD_ARGUMENT;
 if(overlaps(q,sizeof *q,storage,(size_t)capacity*sizeof *storage))
  return AT13_CLKI_BAD_ARGUMENT;
 if(at==AT13_CLKI_NEVER) return AT13_CLKI_BAD_TIME;
 if(level>1) return AT13_CLKI_BAD_LEVEL;
 *q=(attiny13a_clki_input_t){.storage=storage,.now_ps=at,.known_until_ps=at,
  .capacity=capacity,.level=level};
 return AT13_CLKI_OK;
}
int attiny13a_clki_enqueue(attiny13a_clki_input_t *q,
 const attiny13a_clki_edge_t *edges,uint32_t count,uint64_t horizon) {
 if(!valid(q) || (count&&!edges)) return AT13_CLKI_BAD_ARGUMENT;
 if(horizon==AT13_CLKI_NEVER || horizon<q->known_until_ps)
  return AT13_CLKI_BAD_TIME;
 if(count>q->capacity-q->count) return AT13_CLKI_BACKPRESSURE;
 if(count && aliases(q,edges,(size_t)count*sizeof *edges))
  return AT13_CLKI_BAD_ARGUMENT;
 uint64_t previous_time=q->now_ps;
 uint8_t previous_level=q->level;
 if(q->count) {
  const attiny13a_clki_edge_t *tail=&q->storage[index_at(q,q->count-1)];
  previous_time=tail->time_ps;previous_level=tail->level;
 }
 for(uint32_t i=0;i<count;i++) {
  if(edges[i].time_ps==AT13_CLKI_NEVER || edges[i].time_ps<=previous_time ||
     edges[i].time_ps<=q->known_until_ps || edges[i].time_ps>horizon)
   return AT13_CLKI_BAD_TIME;
  if(edges[i].level>1 || edges[i].level==previous_level)
   return AT13_CLKI_BAD_LEVEL;
  previous_time=edges[i].time_ps;previous_level=edges[i].level;
 }
 /* Nothing mutates until the ENTIRE batch and horizon have been checked. */
 uint32_t slot=index_at(q,q->count);
 for(uint32_t i=0;i<count;i++) {
  q->storage[slot]=edges[i];slot=successor(q,slot);
 }
 q->count+=count;q->known_until_ps=horizon;
 return AT13_CLKI_OK;
}
int attiny13a_clki_peek(const attiny13a_clki_input_t *q,attiny13a_clki_edge_t *edge) {
 if(!valid(q) || !edge || aliases(q,edge,sizeof *edge)) return AT13_CLKI_BAD_ARGUMENT;
 if(!q->count) return AT13_CLKI_EMPTY;
 *edge=q->storage[q->head];return AT13_CLKI_OK;
}
int attiny13a_clki_consume(attiny13a_clki_input_t *q,attiny13a_clki_edge_t *edge) {
 if(!valid(q) || (edge&&aliases(q,edge,sizeof *edge))) return AT13_CLKI_BAD_ARGUMENT;
 if(!q->count) return AT13_CLKI_EMPTY;
 const attiny13a_clki_edge_t value=q->storage[q->head];
 if(edge) *edge=value;
 q->head=successor(q,q->head);q->count--;
 q->now_ps=value.time_ps;q->level=value.level;
 return AT13_CLKI_OK;
}
int attiny13a_clki_hold_until(attiny13a_clki_input_t *q,uint64_t at) {
 if(!valid(q)) return AT13_CLKI_BAD_ARGUMENT;
 if(at==AT13_CLKI_NEVER || at<q->now_ps) return AT13_CLKI_BAD_TIME;
 if(at>q->known_until_ps) return AT13_CLKI_UNKNOWN_HORIZON;
 if(q->count && q->storage[q->head].time_ps<=at) return AT13_CLKI_EDGE_PENDING;
 q->now_ps=at;return AT13_CLKI_OK;
}
uint64_t attiny13a_clki_now(const attiny13a_clki_input_t *q) {
 return valid(q)?q->now_ps:AT13_CLKI_NEVER;
}
uint64_t attiny13a_clki_horizon(const attiny13a_clki_input_t *q) {
 return valid(q)?q->known_until_ps:AT13_CLKI_NEVER;
}
uint8_t attiny13a_clki_level(const attiny13a_clki_input_t *q) {
 return valid(q)?q->level:255;
}
uint32_t attiny13a_clki_count(const attiny13a_clki_input_t *q) {
 return valid(q)?q->count:0;
}
uint32_t attiny13a_clki_free(const attiny13a_clki_input_t *q) {
 return valid(q)?q->capacity-q->count:0;
}
