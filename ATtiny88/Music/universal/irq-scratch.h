#ifndef MICROMUSIC_IRQ_SCRATCH_H
#define MICROMUSIC_IRQ_SCRATCH_H
/* Hardware-driver resource choice, independent of musical arithmetic.
 * The stack path owns no GPIOR registers. An explicitly selected GPIOR path
 * exclusively owns GPIOR0/1/2 while the non-nested PWM interrupt is enabled.
 * This header is preprocessor-only and safe to include from assembler. */
#if defined(UM_REQUESTED_IRQ_GPIOR_SCRATCH)
#if UM_REQUESTED_IRQ_GPIOR_SCRATCH != 0 && UM_REQUESTED_IRQ_GPIOR_SCRATCH != 1
#error "UM_REQUESTED_IRQ_GPIOR_SCRATCH must be 0 (stack) or 1 (GPIOR)"
#endif
#if defined(UM_IRQ_GPIOR_SCRATCH) && UM_IRQ_GPIOR_SCRATCH != UM_REQUESTED_IRQ_GPIOR_SCRATCH
#error "UM_IRQ_GPIOR_SCRATCH disagrees with the requested IRQ scratch configuration"
#endif
#ifndef UM_IRQ_GPIOR_SCRATCH
#define UM_IRQ_GPIOR_SCRATCH UM_REQUESTED_IRQ_GPIOR_SCRATCH
#endif
#endif
#ifndef UM_IRQ_GPIOR_SCRATCH
#define UM_IRQ_GPIOR_SCRATCH 0
#endif
#if UM_IRQ_GPIOR_SCRATCH != 0 && UM_IRQ_GPIOR_SCRATCH != 1
#error "UM_IRQ_GPIOR_SCRATCH must be 0 (stack) or 1 (GPIOR)"
#endif
#endif
