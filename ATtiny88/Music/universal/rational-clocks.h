/* Experimental C11 example: exact shorter accumulators, not a new clock rate.
   F_CPU must be a compiler constant; include after the platform clock header.
   Common divisors are selected at compile time. Other clocks retain wide math.
   No register access or assembly. Original MicroMusic code, 2026-10-25. */
#ifndef UM88_REVIEW_RATIONAL_CLOCKS_H
#define UM88_REVIEW_RATIONAL_CLOCKS_H
#include <stdint.h>
#if F_CPU % 75000UL == 0
#define UM_CONTROL_UNIT 75000UL
#elif F_CPU % 25000UL == 0
#define UM_CONTROL_UNIT 25000UL
#else
#define UM_CONTROL_UNIT 1UL
#endif
#if F_CPU % 3200000UL == 0
#define UM_DRUM_UNIT 3200000UL
#elif F_CPU % 2400000UL == 0
#define UM_DRUM_UNIT 2400000UL
#elif F_CPU % 1600000UL == 0
#define UM_DRUM_UNIT 1600000UL
#else
#define UM_DRUM_UNIT 1UL
#endif
#define UM_CONTROL_INCREMENT (75000UL/UM_CONTROL_UNIT)
#define UM_CONTROL_PERIOD (F_CPU/UM_CONTROL_UNIT)
#define UM_DRUM_FRACTION_INCREMENT ((19200000UL%F_CPU)/UM_DRUM_UNIT)
#define UM_DRUM_FRACTION_PERIOD (F_CPU/UM_DRUM_UNIT)
_Static_assert(F_CPU%UM_CONTROL_UNIT==0 && 75000UL%UM_CONTROL_UNIT==0,"Exact control divisor");
_Static_assert(F_CPU%UM_DRUM_UNIT==0 && 19200000UL%UM_DRUM_UNIT==0,"Exact percussion divisor");
#if UM_CONTROL_PERIOD+UM_CONTROL_INCREMENT <= 256UL
typedef uint8_t UMMusicClock;
#elif UM_CONTROL_PERIOD+UM_CONTROL_INCREMENT <= 65536UL
typedef uint16_t UMMusicClock;
#else
typedef uint32_t UMMusicClock;
#endif
#if UM_DRUM_FRACTION_PERIOD+UM_DRUM_FRACTION_INCREMENT <= 256UL
typedef uint8_t UMFraction;
#elif UM_DRUM_FRACTION_PERIOD+UM_DRUM_FRACTION_INCREMENT <= 65536UL
typedef uint16_t UMFraction;
#else
typedef uint32_t UMFraction;
#endif
#endif
