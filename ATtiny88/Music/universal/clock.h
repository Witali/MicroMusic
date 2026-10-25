#ifndef MICROMUSIC_CLOCK_H
#define MICROMUSIC_CLOCK_H
/* A board header supplied with -include may define F_CPU first. */
#if defined(UM_REQUESTED_CPU_HZ) && defined(F_CPU) && F_CPU != UM_REQUESTED_CPU_HZ
#error "F_CPU disagrees with the requested build frequency"
#endif
#ifndef F_CPU
#ifdef UM_REQUESTED_CPU_HZ
#define F_CPU UM_REQUESTED_CPU_HZ
#else
#define F_CPU 8000000UL
#endif
#endif
#if defined(UM_BOARD_MH_ET_LIVE_16MHZ) && UM_BOARD_MH_ET_LIVE_16MHZ
/* This manufacturer's board uses 16 MHz, above ATtiny88's 12-MHz rating.
 * Keep this explicit board configuration outside the ordinary device range. */
#if F_CPU != 16000000UL
#error "MH-ET LIVE Micronucleus board requires F_CPU=16000000 Hz"
#endif
#elif F_CPU < 75000UL || F_CPU > 12000000UL
#error "ATtiny88 F_CPU must be 75000..12000000 Hz; also respect voltage/speed limits"
#endif
#define UM_PWM_DIVIDER 256UL
#define UM_SYNTHESIS_DIVIDER (UM_PWM_DIVIDER*4UL)
#endif
