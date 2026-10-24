#include "timer0.h"

static uint8_t waveform(const timer0_t *t) {
 return (uint8_t)((t->tccra & 3) | ((t->tccrb & 8) >> 1));
}
static int pwm(uint8_t m) { return m == 1 || m == 3 || m == 5 || m == 7; }
static int phase_correct(uint8_t m) { return m == 1 || m == 5; }
static uint8_t top_value(const timer0_t *t, uint8_t m) {
 return m == 2 || m == 5 || m == 7 ? t->active_a : 255;
}
static int held(const timer0_t *t) { return (t->gtccr & 0x81) == 0x81; }
static int clocked(const timer0_t *t) {
 return t->clock_enabled && !(t->prr & 2) && !held(t);
}
static unsigned divisor(const timer0_t *t) {
 static const unsigned periods[8] = {0, 1, 8, 64, 256, 1024, 0, 0};
 return periods[t->tccrb & 7];
}
static int validate(const timer0_t *t) {
 uint8_t m = waveform(t);
 if (m == 4 || m == 6) return TIMER0_RESERVED_WGM;
 if (pwm(m) && ((t->tccra >> 4) & 3) == 1) return TIMER0_RESERVED_COM0B;
 return TIMER0_OK;
}
/* DS40002307A 11.7.4/Table11-8 do not resolve the simultaneous TOP/BOTTOM
 * precedence. A nonzero pending buffer does not establish how to leave this
 * state. Configuration and an edge-free hold are known; its next timer pulse
 * is not. Check before changing TCNT, flags, OC latches or buffered OCR. */
static int uncertain_pulse(const timer0_t *t) {
 return waveform(t) == 5 && !t->active_a;
}
static void capture(timer0_t *t) {
 timer0_event_t *event;
 uint32_t tail;
 if (!t->capacity) return;
 if (t->count) {
  tail = (t->head + t->count - 1) % t->capacity;
  event = &t->events[tail];
  if (event->cycle == t->cycle) {
   event->levels = t->levels;
   event->overrides = t->overrides;
   return;
  }
 }
 if (t->count == t->capacity) {
  if (t->dropped_events != UINT64_MAX) ++t->dropped_events;
  return;
 }
 tail = (t->head + t->count++) % t->capacity;
 event = &t->events[tail];
 event->cycle = t->cycle;
 event->levels = t->levels;
 event->overrides = t->overrides;
 for (unsigned i = 0; i < sizeof(event->reserved); ++i) event->reserved[i] = 0;
}
static void update_mux(timer0_t *t) {
 uint8_t m = waveform(t), a = (t->tccra >> 6) & 3;
 uint8_t b = (t->tccra >> 4) & 3, mask = 0;
 if (a && (!pwm(m) || a > 1 || (m & 4))) mask |= TIMER0_OC0A;
 if (b && (!pwm(m) || b > 1)) mask |= TIMER0_OC0B;
 if (mask != t->overrides) { t->overrides = mask; capture(t); }
}
static void set_level(timer0_t *t, uint8_t bit, int high) {
 uint8_t value = high ? t->levels | bit : t->levels & (uint8_t)~bit;
 if (value != t->levels) { t->levels = value; capture(t); }
}
static void non_pwm_compare(timer0_t *t, int channel) {
 uint8_t bit = (uint8_t)(1u << channel);
 unsigned com = (t->tccra >> (channel ? 4 : 6)) & 3;
 if (com == 1) set_level(t, bit, !(t->levels & bit));
 else if (com >= 2) set_level(t, bit, com == 3);
}
static void compare_output(timer0_t *t, int channel, uint8_t m,
                           uint8_t top, int down) {
 uint8_t bit = (uint8_t)(1u << channel);
 unsigned com = (t->tccra >> (channel ? 4 : 6)) & 3;
 unsigned ocr = channel ? t->active_b : t->active_a;
 if (!pwm(m)) { non_pwm_compare(t, channel); return; }
 if (com == 1 && !channel && (m & 4)) {
  set_level(t, bit, !(t->levels & bit));
 } else if (com >= 2) {
  if (phase_correct(m)) {
   /* The extreme duty values are constant, including the missing up-slope
    * comparison on the very first cycle (DS40002307A 11.7.4). */
   if (ocr == 0) set_level(t, bit, com == 3);
   else if (ocr == top) set_level(t, bit, com == 2);
   else set_level(t, bit, down ? com == 2 : com == 3);
  } else if (ocr != top) {
   /* TOP wins over the compare, yielding a constant extreme-duty output. */
   set_level(t, bit, com == 3);
  }
 }
}
static void bottom_output(timer0_t *t) {
 for (int channel = 0; channel < 2; ++channel) {
  unsigned com = (t->tccra >> (channel ? 4 : 6)) & 3;
  if (com >= 2) set_level(t, (uint8_t)(1u << channel), com == 2);
 }
}
static void phase_top_output(timer0_t *t, uint8_t top) {
 for (int channel = 0; channel < 2; ++channel) {
  unsigned com = (t->tccra >> (channel ? 4 : 6)) & 3;
  unsigned ocr = channel ? t->active_b : t->active_a;
  /* TOP establishes the up-slope result even when its compare was missed,
   * including a buffered OCR change from MAX (11.7.4, figure 11-7). */
  if (com >= 2 && ocr <= top)
   set_level(t, (uint8_t)(1u << channel), ocr == top && ocr ? com == 2 : com == 3);
 }
}
static void load_buffers(timer0_t *t) {
 t->active_a = t->ocra;
 t->active_b = t->ocrb;
}
/* One timer pulse, not one CPU clock. Comparisons use the pre-pulse TCNT0:
 * equality is observed for one timer interval, OCF/OC act on the next pulse.
 * See figures 11-10/11-11. TOV uses the new TCNT0 and is not delayed. */
static void pulse(timer0_t *t) {
 uint8_t m = waveform(t), top = top_value(t, m), old = t->tcnt;
 int block = t->block_compare, down = t->descending;
 int match_a = !block && old == t->active_a;
 int match_b = !block && old == t->active_b;
 t->block_compare = 0;
 if (match_a) { t->tifr |= TIMER0_OCF0A; compare_output(t, 0, m, top, down); }
 if (match_b) { t->tifr |= TIMER0_OCF0B; compare_output(t, 1, m, top, down); }
 if (phase_correct(m)) {
  if (old == top && top) down = t->descending = 1;
  else if (!old) down = t->descending = 0;
  if (down && old) {
   t->tcnt = (uint8_t)(old - 1);
   if (!t->tcnt) { t->descending = 0; t->tifr |= TIMER0_TOV0; }
  } else {
   t->descending = 0;
   t->tcnt = (uint8_t)(old + 1);
   if (t->tcnt == top) {
    t->descending = 1;
    load_buffers(t); phase_top_output(t, top_value(t, m));
   } else if (!t->tcnt) t->tifr |= TIMER0_TOV0;
  }
 } else if (m == 3 || m == 7) {
  if (t->fast_clear || old == top) {
   t->tcnt = 0; t->fast_clear = 0; bottom_output(t);
  } else t->tcnt = (uint8_t)(old + 1);
  if (t->tcnt == top) {
   t->tifr |= TIMER0_TOV0; t->fast_clear = 1;
   /* ATtiny13A table 11-8 specifies TOP for BOTH PWM families. */
   load_buffers(t);
  }
 } else {
  t->tcnt = m == 2 && match_a ? 0 : (uint8_t)(old + 1);
  if (old == 255) t->tifr |= TIMER0_TOV0;
 }
 ++t->scheduled_events;
}
/* Number of pulses until a state boundary. Between boundaries the counter is
 * a linear ramp, so entire CPU-clock/prescaler spans can be skipped at once. */
static unsigned event_distance(const timer0_t *t) {
 uint8_t m = waveform(t), top = top_value(t, m);
 unsigned c = t->tcnt, distance, a, b;
 if (t->block_compare) return 1;
 if (phase_correct(m)) {
  if (t->descending && c) {
   distance = c; /* arrive at BOTTOM */
   a = t->active_a <= c ? c - t->active_a + 1 : 257;
   b = t->active_b <= c ? c - t->active_b + 1 : 257;
  } else {
   distance = c < top ? top - c : c == top ? 1 : 256 - c;
   a = t->active_a >= c ? t->active_a - c + 1 : 257;
   b = t->active_b >= c ? t->active_b - c + 1 : 257;
  }
 } else {
  distance = 256 - c; /* normal/CTC overflow, or missed PWM TOP */
  if ((m == 3 || m == 7)) {
   if (t->fast_clear || c == top) distance = 1;
   else if (c < top) distance = top - c;
  }
  a = ((t->active_a - c) & 255) + 1;
  b = ((t->active_b - c) & 255) + 1;
 }
 if (a < distance) distance = a;
 if (b < distance) distance = b;
 return distance;
}
static void skip_pulses(timer0_t *t, uint64_t count) {
 if (phase_correct(waveform(t)) && t->descending)
  t->tcnt = (uint8_t)(t->tcnt - count);
 else t->tcnt = (uint8_t)(t->tcnt + count);
}
static void elapse(timer0_t *t, uint64_t delta) {
 /* Prescaler runs even with CS=0 or external clock selected. PRR and sleep
  * freeze its phase. Holding PSR10 keeps the phase at zero. */
 if (t->clock_enabled && !(t->prr & 2) && !held(t))
  t->prescaler = (uint16_t)((t->prescaler + (delta & 1023)) & 1023);
 t->cycle += delta;
}
void timer0_init(timer0_t *t, timer0_event_t *events, uint32_t capacity,
                 uint64_t cycle) {
 *t = (timer0_t){0};
 t->clock_enabled = 1;
 t->events = events;
 t->capacity = events ? capacity : 0;
 t->cycle = cycle;
}
uint64_t timer0_next_event(const timer0_t *t) {
 unsigned period = divisor(t);
 uint64_t distance;
 if (!period || !clocked(t) || validate(t)) return UINT64_MAX;
 distance = period - (t->prescaler % period);
 /* Publish the rejected pulse too, so the board stops before crossing an
  * unsupported state rather than giving the CPU a speculative event budget. */
 if (!uncertain_pulse(t)) distance += (uint64_t)(event_distance(t) - 1) * period;
 return distance > UINT64_MAX - t->cycle ? UINT64_MAX : t->cycle + distance;
}
int timer0_advance(timer0_t *t, uint64_t cycle) {
 if (cycle < t->cycle) return TIMER0_TIME_REVERSED;
 while (cycle > t->cycle) {
  uint64_t delta = cycle - t->cycle, pulses = 0;
  unsigned period = divisor(t), distance;
  int error;
  if (!clocked(t) || !(t->tccrb & 7)) { elapse(t, delta); break; }
  error = validate(t);
  if (error) return error;
  if (!period) { elapse(t, delta); break; } /* T0 owned by GPIO synchronizer. */
  if (uncertain_pulse(t)) {
   uint64_t until = period - (t->prescaler % period);
   if (delta < until) { elapse(t, delta); break; }
   /* Retain the last known prefix, including the prescaler before the rejected
    * pulse. Retrying keeps the same deadline; do not silently consume it. */
   elapse(t, until - 1);
   return TIMER0_ZERO_PHASE_TOP;
  }
  pulses = delta / period + ((delta % period + t->prescaler % period) >= period);
  distance = event_distance(t);
  if (pulses < distance) {
   skip_pulses(t, pulses); elapse(t, delta); break;
  }
  delta = period - (t->prescaler % period) + (uint64_t)(distance - 1) * period;
  skip_pulses(t, distance - 1);
  elapse(t, delta);
  pulse(t);
 }
 return TIMER0_OK;
}
int timer0_external_edge(timer0_t *t, uint64_t cycle, int rising) {
 int error = timer0_advance(t, cycle);
 unsigned source = t->tccrb & 7;
 if (error) return error;
 if (!clocked(t) || source != (rising ? 7u : 6u)) return TIMER0_OK;
 error = validate(t);
 if (error) return error;
 if (uncertain_pulse(t)) return TIMER0_ZERO_PHASE_TOP;
 pulse(t);
 return TIMER0_OK;
}
int timer0_set_clock_enabled(timer0_t *t, uint64_t cycle, int enabled) {
 int error = timer0_advance(t, cycle);
 if (error) return error;
 t->clock_enabled = enabled != 0;
 return TIMER0_OK;
}
int timer0_write(timer0_t *t, uint64_t cycle, uint8_t address, uint8_t value) {
 int error = timer0_advance(t, cycle);
 uint8_t before = waveform(t);
 if (error) return error;
 if ((t->prr & 2) && address != TIMER0_PRR) return TIMER0_POWERED_DOWN;
 switch (address) {
 case TIMER0_PRR: t->prr = value & 3; break;
 case TIMER0_GTCCR:
  t->gtccr = value & 0x81;
  if (value & 1) t->prescaler = 0;
  if (!(value & 128)) t->gtccr &= (uint8_t)~1;
  break;
 case TIMER0_TCCR0A: t->tccra = value & 0xf3; break;
 case TIMER0_TCCR0B:
  t->tccrb = value & 15;
  if (!pwm(waveform(t)) && !(waveform(t) == 4 || waveform(t) == 6)) {
   if (value & 128) non_pwm_compare(t, 0);
   if (value & 64) non_pwm_compare(t, 1);
  }
  break;
 case TIMER0_TCNT0: t->tcnt = value; t->block_compare = 1; t->fast_clear = 0; break;
 case TIMER0_OCR0A:
  t->ocra = value;
  if (!pwm(waveform(t))) t->active_a = value;
  break;
 case TIMER0_OCR0B:
  t->ocrb = value;
  if (!pwm(waveform(t))) t->active_b = value;
  break;
 case TIMER0_TIFR0: t->tifr &= (uint8_t)~(value & 14); break;
 case TIMER0_TIMSK0: t->timsk = value & 14; break;
 default: return TIMER0_UNKNOWN_REGISTER;
 }
 if (before != waveform(t)) {
  t->fast_clear = 0;
  if (!pwm(waveform(t))) load_buffers(t);
  if (!phase_correct(waveform(t))) t->descending = 0;
 }
 update_mux(t);
 return TIMER0_OK;
}
int timer0_read(timer0_t *t, uint64_t cycle, uint8_t address, uint8_t *value) {
 int error = timer0_advance(t, cycle);
 if (error) return error;
 if ((t->prr & 2) && address != TIMER0_PRR) return TIMER0_POWERED_DOWN;
 switch (address) {
 case TIMER0_PRR: *value = t->prr; break;
 case TIMER0_GTCCR: *value = t->gtccr; break;
 case TIMER0_TCCR0A: *value = t->tccra; break;
 case TIMER0_TCCR0B: *value = t->tccrb; break;
 case TIMER0_TCNT0: *value = t->tcnt; break;
 case TIMER0_OCR0A: *value = t->ocra; break;
 case TIMER0_OCR0B: *value = t->ocrb; break;
 case TIMER0_TIFR0: *value = t->tifr; break;
 case TIMER0_TIMSK0: *value = t->timsk; break;
 default: return TIMER0_UNKNOWN_REGISTER;
 }
 return TIMER0_OK;
}
uint8_t timer0_irq_pending(const timer0_t *t) { return t->timsk & t->tifr; }
void timer0_irq_ack(timer0_t *t, uint8_t mask) { t->tifr &= (uint8_t)~(mask & 14); }
const timer0_event_t *timer0_events(const timer0_t *t, uint32_t *count) {
 uint32_t contiguous = t->capacity - t->head;
 if (contiguous > t->count) contiguous = t->count;
 *count = contiguous;
 return contiguous ? &t->events[t->head] : NULL;
}
void timer0_consume_events(timer0_t *t, uint32_t count) {
 if (count > t->count) count = t->count;
 if (t->capacity) t->head = (t->head + count) % t->capacity;
 t->count -= count;
}
void timer0_clear_events(timer0_t *t) {
 t->head = 0; t->count = 0; t->dropped_events = 0;
}
