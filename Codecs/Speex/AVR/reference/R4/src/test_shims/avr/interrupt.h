#ifndef AVR_INTERRUPT_H
#define AVR_INTERRUPT_H
#define TIMER2_COMPA_vect __vector_7
#define ISR(n) void n(void) __attribute__((signal,used,externally_visible)); void n(void)
#define sei() __asm__ volatile("sei")
#define cli() __asm__ volatile("cli")
#endif
