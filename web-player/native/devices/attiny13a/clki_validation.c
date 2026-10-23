#include "clki_validation.h"

static int reset_valid(int held) {return held==0 || held==1;}
static int valid(const attiny13a_clki_validation_t *s) {return s && s->initialized==1;}
static void reset_state(attiny13a_clki_validation_t *s,int held) {
 if(s->reset_held==held)return;
 s->reset_held=(uint8_t)held;s->have_comparison_rise=0;s->have_comparison_period=0;
 s->comparison_rise_ps=0;s->comparison_period_ps=0;
}
uint32_t attiny13a_clki_validation_init(attiny13a_clki_validation_t *s,
 uint64_t at,uint8_t level,int held) {
 if(!s || at==UINT64_MAX || level>1 || !reset_valid(held))return AT13_CLKI_VALIDATION_MALFORMED;
 *s=(attiny13a_clki_validation_t){.now_ps=at,.previous_edge_ps=at,
  .level=level,.reset_held=(uint8_t)held,.initialized=1};return 0;
}
uint32_t attiny13a_clki_validation_set_reset(attiny13a_clki_validation_t *s,
 uint64_t at,int held) {
 if(!valid(s) || at==UINT64_MAX || at<s->now_ps || !reset_valid(held))return AT13_CLKI_VALIDATION_MALFORMED;
 reset_state(s,held);s->now_ps=at;return 0;
}
uint32_t attiny13a_clki_validation_edge(attiny13a_clki_validation_t *s,
 uint64_t at,uint8_t level,int32_t vcc,int held) {
 if(!valid(s) || at==UINT64_MAX || at<s->now_ps || at<=s->previous_edge_ps ||
    level>1 || level==s->level || !reset_valid(held))return AT13_CLKI_VALIDATION_MALFORMED;
 uint32_t reason=0;
 uint64_t minimum_period=0,minimum_width=0;
 if(vcc<1800000 || vcc>5500000)reason|=AT13_CLKI_VALIDATION_VOLTAGE;
 else if(vcc>=4500000){minimum_period=50000;minimum_width=20000;}
 else if(vcc>=2700000){minimum_period=100000;minimum_width=40000;}
 else {minimum_period=250000;minimum_width=100000;}
 reset_state(s,held);
 if(s->have_edge && minimum_width && at-s->previous_edge_ps<minimum_width)
  reason|=s->level?AT13_CLKI_VALIDATION_HIGH:AT13_CLKI_VALIDATION_LOW;
 if(level) {
  if(s->have_rise) {
   s->previous_period_ps=at-s->previous_rise_ps;
   if(minimum_period && s->previous_period_ps<minimum_period)reason|=AT13_CLKI_VALIDATION_PERIOD;
  }
  s->previous_rise_ps=at;s->have_rise=1;
  if(!held) {
   if(s->have_comparison_rise) {
    uint64_t period=at-s->comparison_rise_ps;
    if(s->have_comparison_period) {
     uint64_t previous=s->comparison_period_ps;
     uint64_t difference=period>previous?period-previous:previous-period;
     uint64_t smaller=period<previous?period:previous;
     if(difference>smaller/50)reason|=AT13_CLKI_VALIDATION_VARIATION;
    }
    s->comparison_period_ps=period;s->have_comparison_period=1;
   }
   s->comparison_rise_ps=at;s->have_comparison_rise=1;
  }
 }
 s->previous_edge_ps=at;s->have_edge=1;s->level=level;s->now_ps=at;
 s->violations|=reason;return reason;
}
