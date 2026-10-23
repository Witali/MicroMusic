#include "clki_periodic.h"
#include <stddef.h>

static int valid(const attiny13a_clki_periodic_t *s) {
 return s && s->initialized==1 && s->high_ps && s->low_ps &&
  s->initial_level<=1 && s->current_level<=1 && s->next_level==(s->current_level^1) &&
  s->horizon_ps<UINT64_MAX &&
  (s->remaining_edges?s->next_time_ps<=s->horizon_ps:s->next_time_ps==UINT64_MAX);
}
static int add_product(uint64_t *at,uint64_t count,uint64_t duration) {
 if(count && duration>(UINT64_MAX-1-*at)/count)return 0;
 *at+=count*duration;return 1;
}
int attiny13a_clki_periodic_init(attiny13a_clki_periodic_t *s,
 uint64_t start,uint8_t level,uint64_t high,uint64_t low,uint64_t count,uint64_t horizon) {
 if(!s || level>1 || !high || !low)return AT13_CLKI_PERIODIC_BAD_ARGUMENT;
 if(start==UINT64_MAX || horizon==UINT64_MAX || horizon<start)return AT13_CLKI_PERIODIC_BAD_TIME;
 uint64_t final=start,pairs=count/2,first=level?high:low;
 if(!add_product(&final,pairs,high) || !add_product(&final,pairs,low) ||
    !add_product(&final,count&1,first) || final>horizon)return AT13_CLKI_PERIODIC_BAD_TIME;
 *s=(attiny13a_clki_periodic_t){.next_time_ps=count?start+first:UINT64_MAX,
  .high_ps=high,.low_ps=low,.remaining_edges=count,.horizon_ps=horizon,
  .initial_level=level,.current_level=level,.next_level=(uint8_t)(level^1),.initialized=1};
 return AT13_CLKI_PERIODIC_OK;
}
int attiny13a_clki_periodic_peek(const attiny13a_clki_periodic_t *s,attiny13a_clki_edge_t *edge) {
 if(!valid(s) || !edge)return AT13_CLKI_PERIODIC_BAD_ARGUMENT;
 uintptr_t out=(uintptr_t)edge,state=(uintptr_t)s;
 if(out<=state ? state-out<sizeof *edge : out-state<sizeof *s)return AT13_CLKI_PERIODIC_BAD_ARGUMENT;
 if(!s->remaining_edges)return AT13_CLKI_PERIODIC_EMPTY;
 *edge=(attiny13a_clki_edge_t){s->next_time_ps,s->next_level};return AT13_CLKI_PERIODIC_OK;
}
int attiny13a_clki_periodic_consume(attiny13a_clki_periodic_t *s) {
 if(!valid(s))return AT13_CLKI_PERIODIC_BAD_ARGUMENT;
 if(!s->remaining_edges)return AT13_CLKI_PERIODIC_EMPTY;
 uint64_t remaining=s->remaining_edges-1,next=UINT64_MAX;
 uint8_t current=s->next_level;
 if(remaining) {
  uint64_t duration=current?s->high_ps:s->low_ps;
  if(duration>UINT64_MAX-1-s->next_time_ps)return AT13_CLKI_PERIODIC_BAD_TIME;
  next=s->next_time_ps+duration;
  if(next>s->horizon_ps)return AT13_CLKI_PERIODIC_BAD_TIME;
 }
 s->current_level=current;s->next_level=(uint8_t)(current^1);
 s->remaining_edges=remaining;s->next_time_ps=next;return AT13_CLKI_PERIODIC_OK;
}
