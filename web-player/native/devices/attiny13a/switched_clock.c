#include "switched_clock.h"
#include "../../peripherals/device_clock.h"

static int frequency_valid(uint32_t frequency) {return frequency && frequency<=20000000;}
static int enabled_valid(int enabled) {return enabled==0 || enabled==1;}
static int valid(const attiny13a_switched_clock_t *s) {
 return s && s->initialized==1 && frequency_valid(s->frequency_hz) &&
  enabled_valid(s->enabled) && s->time_ps<UINT64_MAX &&
  s->phase<AT13_SWITCHED_CLOCK_PS_PER_SECOND;
}
int attiny13a_switched_clock_init(attiny13a_switched_clock_t *s,
 uint64_t at,uint32_t frequency,int enabled) {
 if(!s || !frequency_valid(frequency) || !enabled_valid(enabled))return AT13_SWITCHED_CLOCK_BAD_ARGUMENT;
 if(at==UINT64_MAX)return AT13_SWITCHED_CLOCK_BAD_TIME;
 *s=(attiny13a_switched_clock_t){.time_ps=at,.frequency_hz=frequency,
  .enabled=(uint8_t)enabled,.initialized=1};return AT13_SWITCHED_CLOCK_OK;
}
int attiny13a_switched_clock_advance(attiny13a_switched_clock_t *s,uint64_t to) {
 if(!valid(s))return AT13_SWITCHED_CLOCK_BAD_ARGUMENT;
 if(to==UINT64_MAX || to<s->time_ps)return AT13_SWITCHED_CLOCK_BAD_TIME;
 uint64_t halves=0,phase=s->phase;
 if(s->enabled && !device_clock_ratio(to-s->time_ps,2ull*s->frequency_hz,s->phase,
     AT13_SWITCHED_CLOCK_PS_PER_SECOND,&halves,&phase))return AT13_SWITCHED_CLOCK_OVERFLOW;
 if(halves>UINT64_MAX-s->source_half)return AT13_SWITCHED_CLOCK_OVERFLOW;
 s->time_ps=to;s->source_half+=halves;s->phase=phase;return AT13_SWITCHED_CLOCK_OK;
}
int attiny13a_switched_clock_set_enabled(attiny13a_switched_clock_t *s,int enabled) {
 if(!valid(s) || !enabled_valid(enabled))return AT13_SWITCHED_CLOCK_BAD_ARGUMENT;
 s->enabled=(uint8_t)enabled;return AT13_SWITCHED_CLOCK_OK;
}
uint64_t attiny13a_switched_clock_deadline_halves(const attiny13a_switched_clock_t *s,uint64_t requested) {
 if(!valid(s))return AT13_SWITCHED_CLOCK_NEVER;
 if(!requested)return s->time_ps;
 if(!s->enabled || requested>UINT64_MAX-s->source_half)return AT13_SWITCHED_CLOCK_NEVER;
 uint64_t whole,remainder;
 /* requested>=1: positive numerator = (requested-1)*1e12+(1e12-phase).
  * Subtract phase BEFORE division, avoiding an overflowing intermediate ceil. */
 if(!device_clock_ratio(requested-1,AT13_SWITCHED_CLOCK_PS_PER_SECOND,
    AT13_SWITCHED_CLOCK_PS_PER_SECOND-s->phase,2ull*s->frequency_hz,&whole,&remainder))
  return AT13_SWITCHED_CLOCK_NEVER;
 if(remainder) {
  if(whole==UINT64_MAX)return AT13_SWITCHED_CLOCK_NEVER;
  whole++;
 }
 if(whole>=UINT64_MAX-s->time_ps)return AT13_SWITCHED_CLOCK_NEVER;
 return s->time_ps+whole;
}
