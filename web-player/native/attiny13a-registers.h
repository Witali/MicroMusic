/* Numeric host/WASM adaptation of the pinned, unmodified Microchip header. */
#ifndef MICROMUSIC_ATTINY13A_REGISTERS_H
#define MICROMUSIC_ATTINY13A_REGISTERS_H

/* This adapter must not be mixed with AVR libc's pointer/lvalue register view. */
#if defined(_AVR_IO_H_) || defined(_SFR_IO8) || defined(_SFR_IO16)
#error "Include the numeric ATtiny13A adapter without avr/io.h or existing SFR macros"
#endif
#define _AVR_IO_H_ 1
#define _SFR_IO8(address) (address)
#define _SFR_IO16(address) (address)
#define _BV(bit) (1u << (bit))
#ifdef __cplusplus
#define AT13_DEFINITION_ASSERT static_assert
#else
#define AT13_DEFINITION_ASSERT _Static_assert
#endif
#include "../vendor/microchip/ATtiny_DFP/3.4.278/include/avr/iotn13a.h"
#include "attiny13a-registers.generated.h"
/* The generated header materializes enums, then removes vendor generic names. */
#undef _AVR_IO_H_
#undef _SFR_IO8
#undef _SFR_IO16
#undef _BV
#undef AT13_DEFINITION_ASSERT

#endif
