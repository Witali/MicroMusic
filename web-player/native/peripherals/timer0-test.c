/* Hardware-contract fixtures and independent jump-versus-cycle scheduling QA. */
#include "timer0.h"

#define CHECK(condition) do { if (!(condition)) return __LINE__; } while (0)
#define WRITE(address, value) CHECK(timer0_write(&t, t.cycle, address, value) == 0)
#define ADVANCE(cycle) CHECK(timer0_advance(&t, cycle) == 0)

static timer0_t t, reference;
static timer0_event_t events[8192], reference_events[8192];
static void reset(void) { timer0_init(&t, events, 8192, 0); }

static int registers(void) {
 uint8_t value = 255;
 reset();
 CHECK(t.cycle == 0 && t.tcnt == 0 && t.levels == 0 && t.overrides == 0);
 CHECK(timer0_next_event(&t) == UINT64_MAX);
 WRITE(TIMER0_TCCR0A, 255); CHECK(t.tccra == 0xf3);
 WRITE(TIMER0_TCCR0B, 0xf0); CHECK(t.tccrb == 0);
 CHECK(timer0_read(&t, 0, TIMER0_TCCR0B, &value) == 0 && value == 0);
 WRITE(TIMER0_TCCR0A, 0);
 WRITE(TIMER0_OCR0A, 42); WRITE(TIMER0_OCR0B, 91);
 CHECK(timer0_read(&t, 0, 0x36, &value) == 0 && value == 42);
 CHECK(timer0_read(&t, 0, 0x29, &value) == 0 && value == 91);
 CHECK(timer0_read(&t, 0, 0x2a, &value) == TIMER0_UNKNOWN_REGISTER);
 CHECK(timer0_write(&t, 0, 0x2a, 1) == TIMER0_UNKNOWN_REGISTER);
 WRITE(TIMER0_TIMSK0, 255); CHECK(t.timsk == 14);
 WRITE(TIMER0_PRR, 255); CHECK(t.prr == 3);
 CHECK(timer0_write(&t, 0, TIMER0_TCNT0, 99) == TIMER0_POWERED_DOWN);
 CHECK(timer0_read(&t, 0, TIMER0_TCNT0, &value) == TIMER0_POWERED_DOWN);
 CHECK(t.tcnt == 0);
 WRITE(TIMER0_PRR, 0);
 WRITE(TIMER0_GTCCR, 255); CHECK(t.gtccr == 0x81);
 WRITE(TIMER0_GTCCR, 1); CHECK(t.gtccr == 0);
 ADVANCE(12);
 CHECK(timer0_advance(&t, 11) == TIMER0_TIME_REVERSED && t.cycle == 12);
 return 0;
}
static int normal_and_irq(void) {
 reset();
 WRITE(TIMER0_OCR0A, 2); WRITE(TIMER0_OCR0B, 4);
 WRITE(TIMER0_TCCR0A, 0x70); /* Toggle A, set B. */
 WRITE(TIMER0_TIMSK0, 14); WRITE(TIMER0_TCCR0B, 1);
 CHECK(timer0_next_event(&t) == 3);
 ADVANCE(2); CHECK(t.tcnt == 2 && t.tifr == 0 && t.levels == 0);
 ADVANCE(3); CHECK(t.tcnt == 3 && t.tifr == 4 && t.levels == 1);
 CHECK(timer0_irq_pending(&t) == 4);
 timer0_irq_ack(&t, 4); CHECK(timer0_irq_pending(&t) == 0);
 ADVANCE(5); CHECK(t.tifr == 8 && t.levels == 3);
 WRITE(TIMER0_TIFR0, 4); CHECK(t.tifr == 8);
 WRITE(TIMER0_TIFR0, 255); CHECK(t.tifr == 0);
 ADVANCE(256); CHECK(t.tcnt == 0 && t.tifr == 2);
 WRITE(TIMER0_TIFR0, 14); WRITE(TIMER0_TCNT0, 2);
 CHECK(timer0_next_event(&t) == 257);
 ADVANCE(257); CHECK(t.tcnt == 3 && t.tifr == 0 && t.block_compare == 0);
 WRITE(TIMER0_TCNT0, 2);
 WRITE(TIMER0_TCCR0B, 0); ADVANCE(400); CHECK(t.block_compare == 1);
 WRITE(TIMER0_TCCR0B, 1); ADVANCE(401); CHECK(!(t.tifr & 4));
 return 0;
}
static int ctc(void) {
 reset();
 WRITE(TIMER0_OCR0A, 3); WRITE(TIMER0_OCR0B, 1);
 WRITE(TIMER0_TCCR0A, 0x52); WRITE(TIMER0_TCCR0B, 1);
 ADVANCE(1); CHECK(t.tcnt == 1 && t.tifr == 0);
 ADVANCE(2); CHECK(t.tcnt == 2 && t.tifr == 8 && t.levels == 2);
 ADVANCE(3); CHECK(t.tcnt == 3 && !(t.tifr & 4));
 ADVANCE(4); CHECK(t.tcnt == 0 && t.tifr == 12 && t.levels == 3);
 ADVANCE(8); CHECK(t.tcnt == 0 && t.levels == 0 && !(t.tifr & 2));
 WRITE(TIMER0_OCR0A, 200); ADVANCE(108); CHECK(t.tcnt == 100);
 WRITE(TIMER0_OCR0A, 50); WRITE(TIMER0_TIFR0, 14);
 ADVANCE(263); CHECK(t.tcnt == 255 && !(t.tifr & 6));
 ADVANCE(264); CHECK(t.tcnt == 0 && (t.tifr & 2));
 ADVANCE(315); CHECK(t.tcnt == 0 && (t.tifr & 4));
 /* Writing the same TOP blocks the match AND its CTC clear for one pulse. */
 WRITE(TIMER0_TCNT0, 50); WRITE(TIMER0_TIFR0, 14);
 ADVANCE(316); CHECK(t.tcnt == 51 && !(t.tifr & 4));
 return 0;
}
static int prescaler_and_gates(void) {
 reset();
 ADVANCE(3); WRITE(TIMER0_TCCR0B, 2);
 ADVANCE(7); CHECK(t.tcnt == 0 && t.prescaler == 7);
 ADVANCE(8); CHECK(t.tcnt == 1 && t.prescaler == 8);
 WRITE(TIMER0_TCCR0B, 0); ADVANCE(25); CHECK(t.tcnt == 1);
 WRITE(TIMER0_TCCR0B, 2); ADVANCE(31); CHECK(t.tcnt == 1);
 ADVANCE(32); CHECK(t.tcnt == 2);
 WRITE(TIMER0_GTCCR, 1); CHECK(t.prescaler == 0 && t.gtccr == 0);
 ADVANCE(39); CHECK(t.tcnt == 2);
 ADVANCE(40); CHECK(t.tcnt == 3);
 WRITE(TIMER0_GTCCR, 0x81); ADVANCE(1000);
 CHECK(t.tcnt == 3 && t.prescaler == 0 && t.gtccr == 0x81);
 WRITE(TIMER0_GTCCR, 0x80); ADVANCE(1008);
 CHECK(t.tcnt == 4 && t.gtccr == 0x80);
 WRITE(TIMER0_GTCCR, 0); ADVANCE(1011); CHECK(t.prescaler == 11);
 WRITE(TIMER0_PRR, 2); ADVANCE(2000);
 CHECK(t.tcnt == 4 && t.prescaler == 11);
 WRITE(TIMER0_PRR, 0); ADVANCE(2004); CHECK(t.tcnt == 4);
 ADVANCE(2005); CHECK(t.tcnt == 5);
 CHECK(timer0_set_clock_enabled(&t, 2005, 0) == 0);
 ADVANCE(3000); CHECK(t.tcnt == 5 && t.prescaler == 16);
 CHECK(timer0_next_event(&t) == UINT64_MAX);
 CHECK(timer0_set_clock_enabled(&t, 3000, 1) == 0);
 ADVANCE(3008); CHECK(t.tcnt == 6);
 /* All prescaler taps share one phase; CS switches do not restart it. */
 WRITE(TIMER0_TCCR0B, 3); ADVANCE(3047); CHECK(t.tcnt == 6);
 ADVANCE(3048); CHECK(t.tcnt == 7);
 WRITE(TIMER0_TCCR0B, 4); ADVANCE(3239); CHECK(t.tcnt == 7);
 ADVANCE(3240); CHECK(t.tcnt == 8);
 WRITE(TIMER0_TCCR0B, 5); ADVANCE(4007); CHECK(t.tcnt == 8);
 ADVANCE(4008); CHECK(t.tcnt == 9 && t.prescaler == 0);
 return 0;
}
static int fast_pwm(void) {
 reset();
 WRITE(TIMER0_OCR0A, 64); WRITE(TIMER0_OCR0B, 128);
 WRITE(TIMER0_TCCR0A, 0xb3); WRITE(TIMER0_TCCR0B, 1);
 ADVANCE(254); CHECK(!(t.tifr & 2));
 ADVANCE(255); CHECK(t.tcnt == 255 && (t.tifr & 2));
 ADVANCE(256); CHECK(t.tcnt == 0 && t.levels == 1);
 ADVANCE(320); CHECK(t.levels == 1);
 ADVANCE(321); CHECK(t.levels == 0);
 ADVANCE(385); CHECK(t.levels == 2);
 WRITE(TIMER0_OCR0A, 200); CHECK(t.ocra == 200 && t.active_a == 64);
 ADVANCE(510); CHECK(t.active_a == 64);
 ADVANCE(511); CHECK(t.active_a == 200); /* ATtiny13A TOP latch. */
 ADVANCE(512); CHECK(t.levels == 1);
 ADVANCE(712); CHECK(t.levels == 3);
 ADVANCE(713); CHECK(t.levels == 2);
 /* Narrow OCR=0 pulse lasts one timer clock. OCR=TOP is constant. */
 reset(); WRITE(TIMER0_OCR0A, 0); WRITE(TIMER0_OCR0B, 255);
 WRITE(TIMER0_TCCR0A, 0xa3); WRITE(TIMER0_TCCR0B, 1);
 ADVANCE(256); CHECK(t.levels == 3);
 ADVANCE(257); CHECK(t.levels == 2);
 ADVANCE(511); CHECK(t.levels == 2);
 ADVANCE(512); CHECK(t.levels == 3);
 return 0;
}
static int variable_pwm(void) {
 reset(); WRITE(TIMER0_OCR0A, 3); WRITE(TIMER0_OCR0B, 1);
 WRITE(TIMER0_TCCR0A, 0x63); WRITE(TIMER0_TCCR0B, 9);
 CHECK(t.overrides == 3);
 ADVANCE(3); CHECK(t.tcnt == 3 && t.tifr == 10 && t.levels == 0);
 ADVANCE(4); CHECK(t.tcnt == 0 && t.tifr == 14 && t.levels == 3);
 ADVANCE(6); CHECK(t.levels == 1);
 ADVANCE(8); CHECK(t.levels == 2);
 WRITE(TIMER0_OCR0A, 5); CHECK(t.active_a == 3 && t.ocra == 5);
 ADVANCE(11); CHECK(t.active_a == 5 && t.tcnt == 3 && t.fast_clear);
 ADVANCE(12); CHECK(t.tcnt == 0); /* Pending clear survives TOP increase. */
 ADVANCE(17); CHECK(t.tcnt == 5 && t.fast_clear);
 ADVANCE(18); CHECK(t.tcnt == 0);
 reset(); WRITE(TIMER0_OCR0A, 0); WRITE(TIMER0_TCCR0A, 0x43);
 WRITE(TIMER0_TCCR0B, 9); ADVANCE(1);
 CHECK(t.tcnt == 0 && t.levels == 1 && (t.tifr & 6) == 6);
 ADVANCE(2); CHECK(t.tcnt == 0 && t.levels == 0);
 return 0;
}
static int phase_pwm(void) {
 reset(); WRITE(TIMER0_OCR0A, 255); WRITE(TIMER0_OCR0B, 64);
 WRITE(TIMER0_TCCR0A, 0xa1); WRITE(TIMER0_TCCR0B, 1);
 ADVANCE(255); CHECK(t.tcnt == 255 && t.descending && t.levels == 1);
 ADVANCE(256); CHECK(t.tcnt == 254 && (t.tifr & 4));
 ADVANCE(446); CHECK(t.tcnt == 64 && t.levels == 1);
 ADVANCE(447); CHECK(t.tcnt == 63 && t.levels == 3);
 ADVANCE(509); CHECK(t.tcnt == 1 && !(t.tifr & 2));
 ADVANCE(510); CHECK(t.tcnt == 0 && !t.descending && (t.tifr & 2));
 WRITE(TIMER0_OCR0B, 0); CHECK(t.active_b == 64);
 ADVANCE(764); CHECK(t.active_b == 64);
 ADVANCE(765); CHECK(t.active_b == 0 && t.levels == 1);
 ADVANCE(1020); CHECK(t.levels == 1);
 /* A new non-extreme OCR must reset the old MAX-level at TOP. */
 reset(); WRITE(TIMER0_OCR0A, 255); WRITE(TIMER0_TCCR0A, 0x81);
 WRITE(TIMER0_TCCR0B, 1); ADVANCE(255); CHECK(t.levels == 1);
 WRITE(TIMER0_OCR0A, 128); ADVANCE(764); CHECK(t.levels == 1);
 ADVANCE(765); CHECK(t.active_a == 128 && t.levels == 0);
 ADVANCE(893); CHECK(t.levels == 1);
 /* Variable TOP: 0,1,2,3,2,1,0 (period = 2*TOP). */
 reset(); WRITE(TIMER0_OCR0A, 3); WRITE(TIMER0_OCR0B, 1);
 WRITE(TIMER0_TCCR0A, 0xe1); WRITE(TIMER0_TCCR0B, 9);
 ADVANCE(3); CHECK(t.tcnt == 3 && t.descending && t.levels == 0);
 ADVANCE(4); CHECK(t.tcnt == 2);
 ADVANCE(5); CHECK(t.tcnt == 1 && !(t.tifr & 2));
 ADVANCE(6); CHECK(t.tcnt == 0 && t.levels == 2 && (t.tifr & 2));
 ADVANCE(8); CHECK(t.tcnt == 2 && t.levels == 0);
 return 0;
}
static int force_and_mux(void) {
 uint8_t value = 255;
 reset(); WRITE(TIMER0_OCR0A, 12); WRITE(TIMER0_TCCR0A, 0x72);
 WRITE(TIMER0_TCCR0B, 0xc0);
 CHECK(t.levels == 3 && t.tcnt == 0 && t.tifr == 0 && t.overrides == 3);
 CHECK(timer0_read(&t, 0, TIMER0_TCCR0B, &value) == 0 && value == 0);
 WRITE(TIMER0_TCCR0B, 0x80); CHECK(t.levels == 2 && t.tifr == 0);
 WRITE(TIMER0_TCCR0A, 0); CHECK(t.levels == 2 && t.overrides == 0);
 WRITE(TIMER0_TCCR0A, 0x41); CHECK(t.overrides == 0); /* COMA1 disconnected PWM */
 WRITE(TIMER0_TCCR0B, 8); CHECK(t.overrides == 1);
 WRITE(TIMER0_TCCR0B, 0xc8); CHECK(t.levels == 2 && t.tifr == 0);
 /* Output latches survive mux disconnects and WGM changes. */
 WRITE(TIMER0_TCCR0A, 0xa0); WRITE(TIMER0_TCCR0B, 0xc0);
 CHECK(t.levels == 0 && t.overrides == 3);
 WRITE(TIMER0_TCCR0A, 0xf0); WRITE(TIMER0_TCCR0B, 0xc0);
 CHECK(t.levels == 3);
 return 0;
}
static int external_clock(void) {
 reset(); WRITE(TIMER0_OCR0A, 1); WRITE(TIMER0_TCCR0B, 6);
 ADVANCE(100); CHECK(t.tcnt == 0 && t.prescaler == 100);
 CHECK(timer0_next_event(&t) == UINT64_MAX);
 CHECK(timer0_external_edge(&t, 100, 1) == 0 && t.tcnt == 0);
 CHECK(timer0_external_edge(&t, 103, 0) == 0 && t.tcnt == 1);
 CHECK(timer0_external_edge(&t, 107, 0) == 0 && t.tcnt == 2 && (t.tifr & 4));
 WRITE(TIMER0_TCCR0B, 7);
 CHECK(timer0_external_edge(&t, 111, 0) == 0 && t.tcnt == 2);
 CHECK(timer0_external_edge(&t, 115, 1) == 0 && t.tcnt == 3);
 WRITE(TIMER0_GTCCR, 0x81);
 CHECK(timer0_external_edge(&t, 119, 1) == 0 && t.tcnt == 3);
 WRITE(TIMER0_GTCCR, 0); WRITE(TIMER0_PRR, 2);
 CHECK(timer0_external_edge(&t, 123, 1) == 0 && t.tcnt == 3);
 WRITE(TIMER0_PRR, 0); WRITE(TIMER0_TCNT0, 1); WRITE(TIMER0_TIFR0, 14);
 CHECK(timer0_external_edge(&t, 127, 1) == 0 && t.tcnt == 2 && !(t.tifr & 4));
 CHECK(timer0_external_edge(&t, 126, 1) == TIMER0_TIME_REVERSED);
 return 0;
}
static int capture_ring(void) {
 uint32_t count;
 const timer0_event_t *batch;
 timer0_init(&t, events, 2, 0);
 WRITE(TIMER0_TCCR0A, 0xc0); WRITE(TIMER0_TCCR0B, 0x80);
 CHECK(t.count == 1 && events[0].cycle == 0 && events[0].levels == 1);
 ADVANCE(1); WRITE(TIMER0_TCCR0A, 0x40); WRITE(TIMER0_TCCR0B, 0x80);
 CHECK(t.count == 2 && events[1].cycle == 1 && events[1].levels == 0);
 ADVANCE(2); WRITE(TIMER0_TCCR0B, 0x80);
 CHECK(t.count == 2 && t.dropped_events == 1 && t.levels == 1);
 batch = timer0_events(&t, &count); CHECK(batch == events && count == 2);
 timer0_consume_events(&t, 1); CHECK(t.count == 1 && t.head == 1);
 ADVANCE(3); WRITE(TIMER0_TCCR0B, 0x80);
 CHECK(t.count == 2 && events[0].cycle == 3 && events[0].levels == 0);
 batch = timer0_events(&t, &count); CHECK(batch == events + 1 && count == 1);
 timer0_consume_events(&t, 1);
 batch = timer0_events(&t, &count); CHECK(batch == events && count == 1);
 timer0_consume_events(&t, 999);
 CHECK(!timer0_events(&t, &count) && count == 0);
 timer0_clear_events(&t); CHECK(t.dropped_events == 0 && t.head == 0);
 timer0_init(&t, NULL, 128, 0); WRITE(TIMER0_TCCR0A, 0xc0);
 WRITE(TIMER0_TCCR0B, 0x80); CHECK(t.capacity == 0 && t.dropped_events == 0);
 return 0;
}
static uint32_t random_state;
static uint32_t next_random(void) {
 random_state = random_state * 1664525u + 1013904223u;
 return random_state;
}
static int same_state(void) {
 CHECK(t.cycle == reference.cycle && t.prescaler == reference.prescaler);
 CHECK(t.tccra == reference.tccra && t.tccrb == reference.tccrb);
 CHECK(t.tcnt == reference.tcnt && t.tifr == reference.tifr && t.timsk == reference.timsk);
 CHECK(t.active_a == reference.active_a && t.active_b == reference.active_b);
 CHECK(t.ocra == reference.ocra && t.ocrb == reference.ocrb);
 CHECK(t.descending == reference.descending && t.block_compare == reference.block_compare);
 CHECK(t.fast_clear == reference.fast_clear && t.gtccr == reference.gtccr && t.prr == reference.prr);
 CHECK(t.levels == reference.levels && t.overrides == reference.overrides);
 CHECK(t.count == reference.count && t.dropped_events == reference.dropped_events);
 for (uint32_t i = 0; i < t.count; ++i) {
  CHECK(events[i].cycle == reference_events[i].cycle);
  CHECK(events[i].levels == reference_events[i].levels);
  CHECK(events[i].overrides == reference_events[i].overrides);
 }
 return 0;
}
static int scheduler_differential(void) {
 static const uint8_t addresses[] = {TIMER0_TCNT0, TIMER0_OCR0A, TIMER0_OCR0B,
  TIMER0_TIFR0, TIMER0_TIMSK0, TIMER0_GTCCR, TIMER0_PRR};
 static const uint8_t modes[] = {0,1,2,3,5,7};
 random_state = 0x13a;
 for (unsigned m = 0; m < sizeof(modes); ++m) {
  reset(); timer0_init(&reference, reference_events, 8192, 0);
  WRITE(TIMER0_OCR0A, 255);
  CHECK(timer0_write(&reference, 0, TIMER0_OCR0A, 255) == 0);
  WRITE(TIMER0_TCCR0A, (uint8_t)(0xb0 | (modes[m] & 3)));
  WRITE(TIMER0_TCCR0B, (uint8_t)(1 | ((modes[m] & 4) << 1)));
  CHECK(timer0_write(&reference, 0, TIMER0_TCCR0A, t.tccra) == 0);
  CHECK(timer0_write(&reference, 0, TIMER0_TCCR0B, t.tccrb) == 0);
  for (unsigned i = 0; i < 1500; ++i) {
   uint64_t horizon = t.cycle + (next_random() % 513);
   uint64_t deadline = timer0_next_event(&t);
   if (deadline > t.cycle && deadline <= horizon) {
    uint64_t prior_events = t.scheduled_events;
    ADVANCE(deadline - 1); CHECK(t.scheduled_events == prior_events);
   }
   int error = timer0_advance(&t, horizon);
   while (reference.cycle < horizon)
    if (timer0_advance(&reference, reference.cycle + 1)) break;
   CHECK(error == 0 || error == TIMER0_ZERO_PHASE_TOP);
   if (error) {
    CHECK(t.cycle == reference.cycle && same_state() == 0);
    CHECK(timer0_write(&t, t.cycle, TIMER0_OCR0A, 255) == 0);
    CHECK(timer0_write(&reference, reference.cycle, TIMER0_OCR0A, 255) == 0);
    horizon = t.cycle;
   }
   CHECK(same_state() == 0);
   uint8_t address = addresses[next_random() % sizeof(addresses)];
   uint8_t value = (uint8_t)(next_random() >> 16);
   if (address == TIMER0_GTCCR) value &= 0x81;
   error = timer0_write(&t, horizon, address, value);
   CHECK(error == 0 || error == TIMER0_POWERED_DOWN);
   CHECK(timer0_write(&reference, horizon, address, value) == error);
   if ((i & 15) == 0) {
    /* Change prescaler/source while preserving the selected WGM. */
    value = (uint8_t)((t.tccrb & 8) | (next_random() % 6));
    error = timer0_write(&t, horizon, TIMER0_TCCR0B, value);
    CHECK(timer0_write(&reference, horizon, TIMER0_TCCR0B, value) == error);
   }
   CHECK(same_state() == 0);
   timer0_clear_events(&t); timer0_clear_events(&reference);
  }
 }
 return 0;
}
static int zero_top_uncertainty(void) {
 uint8_t value;
 /* Pending OCR3 cannot prove a TOP0 buffer transfer, overflow or OC change.
  * A TCNT write suppresses compare only; it does not resolve TOP/BOTTOM. */
 reset(); WRITE(TIMER0_TCCR0A, 0xf0); WRITE(TIMER0_TCCR0B, 0xc0);
 CHECK(t.levels == 3);
 WRITE(TIMER0_TCCR0A, 0x61); WRITE(TIMER0_TCCR0B, 9);
 WRITE(TIMER0_OCR0A, 3); WRITE(TIMER0_OCR0B, 1); WRITE(TIMER0_TCNT0, 0);
 timer0_clear_events(&t);
 CHECK(t.active_a == 0 && t.ocra == 3 && t.active_b == 0 && t.ocrb == 1);
 CHECK(timer0_next_event(&t) == 1);
 value = 255; CHECK(timer0_read(&t, 0, TIMER0_OCR0A, &value) == 0 && value == 3);
 value = 255;
 CHECK(timer0_read(&t, 1, TIMER0_OCR0A, &value) == TIMER0_ZERO_PHASE_TOP && value == 255);
 CHECK(timer0_write(&t, 1, TIMER0_TCNT0, 99) == TIMER0_ZERO_PHASE_TOP);
 CHECK(timer0_advance(&t, 100) == TIMER0_ZERO_PHASE_TOP);
 CHECK(t.cycle == 0 && t.prescaler == 0 && t.tcnt == 0 && t.block_compare == 1);
 CHECK(t.active_a == 0 && t.active_b == 0 && t.ocra == 3 && t.ocrb == 1);
 CHECK(t.tifr == 0 && t.levels == 3 && t.count == 0 && t.scheduled_events == 0);
 CHECK(timer0_next_event(&t) == 1);
 CHECK(timer0_advance(&t, 1) == TIMER0_ZERO_PHASE_TOP && t.cycle == 0);

 /* Free-running prescaler: no error before the selected pulse. A long call
  * keeps its known prefix and retries the same rejected boundary. */
 reset(); ADVANCE(3); WRITE(TIMER0_TCCR0A, 1);
 WRITE(TIMER0_OCR0A, 3); WRITE(TIMER0_TCCR0B, 10);
 CHECK(timer0_next_event(&t) == 8);
 ADVANCE(7); CHECK(t.prescaler == 7 && t.tcnt == 0);
 CHECK(timer0_advance(&t, 100) == TIMER0_ZERO_PHASE_TOP && t.cycle == 7);
 CHECK(t.prescaler == 7 && t.active_a == 0 && t.ocra == 3 && t.tifr == 0);
 CHECK(timer0_next_event(&t) == 8);
 CHECK(timer0_advance(&t, 8) == TIMER0_ZERO_PHASE_TOP && t.cycle == 7);
 CHECK(timer0_set_clock_enabled(&t, 8, 0) == TIMER0_ZERO_PHASE_TOP && t.clock_enabled);
 /* Gates asserted in the known prefix stop the pulse; elapsed wall time is
  * not an unsupported counter transition. */
 WRITE(TIMER0_PRR, 2); CHECK(timer0_next_event(&t) == UINT64_MAX);
 ADVANCE(1000); CHECK(t.prescaler == 7 && t.tcnt == 0);
 WRITE(TIMER0_PRR, 0); CHECK(timer0_next_event(&t) == 1001);
 CHECK(timer0_set_clock_enabled(&t, 1000, 0) == 0);
 ADVANCE(2000); CHECK(t.prescaler == 7);
 CHECK(timer0_set_clock_enabled(&t, 2000, 1) == 0);
 CHECK(timer0_next_event(&t) == 2001);
 WRITE(TIMER0_GTCCR, 0x81); ADVANCE(3000);
 CHECK(t.prescaler == 0 && timer0_next_event(&t) == UINT64_MAX);
 WRITE(TIMER0_GTCCR, 0); CHECK(timer0_next_event(&t) == 3008);
 CHECK(timer0_advance(&t, 3008) == TIMER0_ZERO_PHASE_TOP && t.cycle == 3007);
 CHECK(t.prescaler == 7 && t.active_a == 0 && t.ocra == 3);

 /* CS0 is a valid stopped configuration. External T0 has no autonomous pulse,
  * and only the selected polarity with an enabled clock can reach uncertainty. */
 reset(); WRITE(TIMER0_TCCR0A, 1); WRITE(TIMER0_TCCR0B, 8);
 WRITE(TIMER0_OCR0A, 3); ADVANCE(1000000);
 CHECK(t.tcnt == 0 && t.active_a == 0 && t.ocra == 3 && t.tifr == 0);
 CHECK(timer0_next_event(&t) == UINT64_MAX);
 for (int rising = 0; rising < 2; ++rising) {
  reset(); WRITE(TIMER0_TCCR0A, 0x61);
  WRITE(TIMER0_OCR0A, 3); WRITE(TIMER0_OCR0B, 1);
  WRITE(TIMER0_TCCR0B, (uint8_t)(8 | (rising ? 7 : 6)));
  CHECK(timer0_next_event(&t) == UINT64_MAX);
  ADVANCE(1000); CHECK(t.active_a == 0 && t.tcnt == 0 && t.tifr == 0);
  CHECK(timer0_external_edge(&t, 1001, !rising) == 0);
  CHECK(timer0_set_clock_enabled(&t, 1001, 0) == 0);
  CHECK(timer0_external_edge(&t, 1002, rising) == 0);
  CHECK(timer0_set_clock_enabled(&t, 1002, 1) == 0);
  WRITE(TIMER0_PRR, 2); CHECK(timer0_external_edge(&t, 1003, rising) == 0);
  WRITE(TIMER0_PRR, 0); WRITE(TIMER0_GTCCR, 0x81);
  CHECK(timer0_external_edge(&t, 1004, rising) == 0);
  WRITE(TIMER0_GTCCR, 0); timer0_clear_events(&t);
  CHECK(timer0_external_edge(&t, 1005, rising) == TIMER0_ZERO_PHASE_TOP);
  CHECK(t.cycle == 1005 && t.tcnt == 0 && t.active_a == 0 && t.ocra == 3);
  CHECK(t.active_b == 0 && t.ocrb == 1 && t.tifr == 0 && t.scheduled_events == 0 && !t.count);
  CHECK(timer0_external_edge(&t, 1005, rising) == TIMER0_ZERO_PHASE_TOP);
 }

 /* A known nonzero-TOP prefix may latch zero before the uncertainty boundary.
  * Jump and short advance agree through that prefix, including existing IRQs. */
 for (unsigned period = 1; period <= 8; period += 7) {
  reset(); WRITE(TIMER0_OCR0A, 3); WRITE(TIMER0_OCR0B, 1);
  WRITE(TIMER0_TIMSK0, 14); WRITE(TIMER0_TCCR0A, 0x61);
  WRITE(TIMER0_TCCR0B, (uint8_t)(period == 1 ? 9 : 10));
  ADVANCE(period); WRITE(TIMER0_OCR0A, 0);
  reference = t; reference.events = reference_events;
  for (uint32_t i = 0; i < t.count; ++i) reference_events[i] = events[i];
  CHECK(timer0_advance(&reference, period * 4 - 1) == 0);
  CHECK(timer0_advance(&t, period * 100) == TIMER0_ZERO_PHASE_TOP);
  CHECK(same_state() == 0);
  CHECK(t.scheduled_events == reference.scheduled_events && t.scheduled_events == 2);
  CHECK(t.cycle == period * 4 - 1 && t.tcnt == 3 && t.descending);
  CHECK(t.active_a == 0 && t.ocra == 0 && t.tifr == TIMER0_OCF0B);
  CHECK(timer0_irq_pending(&t) == TIMER0_OCF0B && timer0_next_event(&t) == period * 4);
  WRITE(TIMER0_OCR0A, 3);
  CHECK(timer0_advance(&t, period * 4) == TIMER0_ZERO_PHASE_TOP);
  CHECK(t.cycle == period * 4 - 1 && t.active_a == 0 && t.tcnt == 3);
 }

 /* Reset discards the rejected state. Non-PWM preload before selecting WGM5
  * establishes active TOP3 without requiring an invented zero-TOP pulse. */
 reset(); CHECK(t.tccra == 0 && t.tccrb == 0 && t.scheduled_events == 0);
 WRITE(TIMER0_OCR0A, 3); WRITE(TIMER0_OCR0B, 1);
 CHECK(t.active_a == 3 && t.active_b == 1);
 WRITE(TIMER0_TCCR0A, 0x61); WRITE(TIMER0_TCCR0B, 9);
 ADVANCE(6); CHECK(t.tcnt == 0 && t.active_a == 3 && t.scheduled_events == 4);
 CHECK((t.tifr & 14) == 14 && timer0_next_event(&t) == 8);
 return 0;
}
static int deadlines_and_boundaries(void) {
 timer0_init(&t, NULL, 0, UINT64_C(1) << 40);
 WRITE(TIMER0_OCR0A, 100); WRITE(TIMER0_OCR0B, 200);
 WRITE(TIMER0_TCCR0B, 1);
 CHECK(timer0_next_event(&t) == (UINT64_C(1) << 40) + 101);
 ADVANCE((UINT64_C(1) << 40) + (UINT64_C(1) << 20));
 CHECK(t.tcnt == 0 && t.scheduled_events == 3 * 4096);
 reset(); WRITE(TIMER0_TCCR0B, 9); /* Reserved WGM4. */
 CHECK(timer0_advance(&t, 1) == TIMER0_RESERVED_WGM && t.cycle == 0);
 WRITE(TIMER0_TCCR0A, 0x11); /* PWM with reserved COM0B=1. */
 CHECK(timer0_advance(&t, 1) == TIMER0_RESERVED_COM0B && t.cycle == 0);
 WRITE(TIMER0_TCCR0A, 0); WRITE(TIMER0_TCCR0B, 0);
 WRITE(TIMER0_OCR0A, 255); WRITE(TIMER0_TCCR0A, 1);
 WRITE(TIMER0_TCCR0B, 9); ADVANCE(1);
 reset(); WRITE(TIMER0_TCCR0A, 1); WRITE(TIMER0_TCCR0B, 9);
 CHECK(timer0_advance(&t, 1) == TIMER0_ZERO_PHASE_TOP && t.cycle == 0);
 WRITE(TIMER0_OCR0A, 3);
 CHECK(timer0_advance(&t, 1) == TIMER0_ZERO_PHASE_TOP && t.active_a == 0 && t.ocra == 3);
 timer0_init(&t, NULL, 0, UINT64_MAX - 1);
 WRITE(TIMER0_TCCR0B, 1); ADVANCE(UINT64_MAX);
 CHECK(t.tcnt == 1 && timer0_next_event(&t) == UINT64_MAX);
 return zero_top_uncertainty();
}

int timer0_test_case(unsigned index) {
 switch (index) {
 case 0: return registers();
 case 1: return normal_and_irq();
 case 2: return ctc();
 case 3: return prescaler_and_gates();
 case 4: return fast_pwm();
 case 5: return variable_pwm();
 case 6: return phase_pwm();
 case 7: return force_and_mux();
 case 8: return external_clock();
 case 9: return capture_ring();
 case 10: return scheduler_differential();
 case 11: return deadlines_and_boundaries();
 default: return -1;
 }
}
