#include "clki_clock.h"
#include <stddef.h>

static int divisor_valid(uint32_t divisor) {
 return divisor && divisor<=256 && !(divisor&(divisor-1));
}
static int state_valid(const attiny13a_clki_clock_t *s) {
 return s && divisor_valid(s->divisor) && s->input_level<=1 && s->output_level<=1 &&
  s->source_counter<(s->divisor==1?1:s->divisor/2) &&
  (!s->pending_divisor || divisor_valid(s->pending_divisor)) &&
  s->pending_wait_old_rise==(s->pending_divisor!=0);
}
int attiny13a_clki_clock_init(attiny13a_clki_clock_t *s,uint8_t level,uint32_t divisor) {
 if(!s || level>1 || !divisor_valid(divisor)) return AT13_CLKI_CLOCK_BAD_ARGUMENT;
 *s=(attiny13a_clki_clock_t){.divisor=(uint16_t)divisor,
  .input_level=level,.output_level=divisor==1?level:0};
 return AT13_CLKI_CLOCK_OK;
}
int attiny13a_clki_clock_edge(attiny13a_clki_clock_t *s,
 uint8_t level,int running,uint8_t *output) {
 if(!state_valid(s) || level>1 || level==s->input_level ||
    (running!=0&&running!=1) || !output) return AT13_CLKI_CLOCK_BAD_ARGUMENT;
 uintptr_t at=(uintptr_t)output,start=(uintptr_t)s;
 if(at>=start && at-start<sizeof *s) return AT13_CLKI_CLOCK_BAD_ARGUMENT;
 s->input_level=level;
 if(!running) return AT13_CLKI_CLOCK_NONE;
 uint8_t previous=s->output_level;
 if(s->divisor==1) s->output_level=level;
 else if(level && ++s->source_counter==s->divisor/2) {
  s->source_counter=0;s->output_level^=1;
 }
 if(s->output_level==previous) return AT13_CLKI_CLOCK_NONE;
 if(s->output_level && s->pending_wait_old_rise) {
  s->divisor=s->pending_divisor;s->pending_divisor=0;
  s->pending_wait_old_rise=0;s->source_counter=0;
 }
 *output=s->output_level;
 return AT13_CLKI_CLOCK_TRANSITION;
}
int attiny13a_clki_clock_request_divisor(attiny13a_clki_clock_t *s,uint32_t divisor) {
 if(!state_valid(s) || !divisor_valid(divisor)) return AT13_CLKI_CLOCK_BAD_ARGUMENT;
 s->pending_divisor=(uint16_t)divisor;s->pending_wait_old_rise=1;
 return AT13_CLKI_CLOCK_OK;
}
int attiny13a_clki_clock_reset_divisor(attiny13a_clki_clock_t *s,uint32_t divisor) {
 if(!state_valid(s) || !divisor_valid(divisor)) return AT13_CLKI_CLOCK_BAD_ARGUMENT;
 s->divisor=(uint16_t)divisor;s->source_counter=0;
 s->pending_divisor=0;s->pending_wait_old_rise=0;
 return AT13_CLKI_CLOCK_OK;
}
