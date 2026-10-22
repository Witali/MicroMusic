#pragma once
// Syntax checking ONLY, no real ISR semantics.
#define ISR(vector) void vector(void)
#define TIMER1_COMPA_vect timer1_compa_mock_vector
#define TIMER0_COMPA_vect timer0_compa_mock_vector
