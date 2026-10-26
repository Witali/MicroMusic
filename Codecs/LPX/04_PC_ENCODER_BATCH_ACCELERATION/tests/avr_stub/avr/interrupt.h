#pragma once
#define TIMER1_OVF_vect timer1_overflow_isr
#define TIMER0_COMPA_vect timer0_compa_isr
#define ISR(v) void v(void)
