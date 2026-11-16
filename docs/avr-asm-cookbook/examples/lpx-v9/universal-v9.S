/* Standalone LPX v9 player for the measured AVR25 and AVR5 configurations. */
#if !defined(LPX4_ENABLE_ASM) || !LPX4_ENABLE_ASM
#error Select LPX4_ENABLE_ASM=1 for this entry point, or build the C decoder.
#endif

#ifndef LPX_AUDIO_FILE
#define LPX_AUDIO_FILE "audio.lpx"
#endif

#include "common/abi.inc"
#include "common/lpc-tap.inc"

#if defined(__AVR_ATtiny88__) && __AVR_ARCH__ == 25 && !defined(__AVR_HAVE_MUL__)
#include "attiny88/firmware.inc"
#elif (defined(__AVR_ATmega328__) || defined(__AVR_ATmega328P__)) && \
    __AVR_ARCH__ == 5 && defined(__AVR_HAVE_MUL__)
#include "atmega328p/firmware.inc"
#else
#error LPX v9 assembly player supports ATtiny88, ATmega328 and ATmega328P.
#endif
