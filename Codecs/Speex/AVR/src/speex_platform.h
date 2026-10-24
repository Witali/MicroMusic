/* Port configuration for the restricted, fixed-point NB3 decoder.
 * Override settings with -D or an optional SPEEX_NB3_PLATFORM_HEADER.
 * The C backend contains no handwritten assembly; Flash access is independent
 * of arithmetic selection, so C also works on Harvard-memory AVR devices. */
#ifndef MICROMUSIC_SPEEX_PLATFORM_H
#define MICROMUSIC_SPEEX_PLATFORM_H
#include <stdint.h>
#include <limits.h>
/* Values are available inside a manufacturer's/platform configuration header. */
#define SPEEX_NB3_ARCH_GENERIC 0
#define SPEEX_NB3_ARCH_AVR 1
#define SPEEX_NB3_ARCH_ARM 2
#define SPEEX_NB3_ARCH_RISCV 3
#ifdef SPEEX_NB3_PLATFORM_HEADER
#include SPEEX_NB3_PLATFORM_HEADER
#endif

#ifndef SPEEX_ENABLE_WB1
#define SPEEX_ENABLE_WB1 0
#endif
#if SPEEX_ENABLE_WB1 != 0 && SPEEX_ENABLE_WB1 != 1
#error SPEEX_ENABLE_WB1 must be 0 or 1
#endif

#ifndef SPEEX_NB3_ARCH
#if defined(__AVR__)
#define SPEEX_NB3_ARCH SPEEX_NB3_ARCH_AVR
#elif defined(__arm__) || defined(__thumb__) || defined(__aarch64__) || defined(_M_ARM) || defined(_M_ARM64)
#define SPEEX_NB3_ARCH SPEEX_NB3_ARCH_ARM
#elif defined(__riscv)
#define SPEEX_NB3_ARCH SPEEX_NB3_ARCH_RISCV
#else
#define SPEEX_NB3_ARCH SPEEX_NB3_ARCH_GENERIC
#endif
#endif
#ifndef SPEEX_NB3_ENABLE_ASM
#define SPEEX_NB3_ENABLE_ASM 0
#endif
#if SPEEX_NB3_ENABLE_ASM != 0 && SPEEX_NB3_ENABLE_ASM != 1
#error SPEEX_NB3_ENABLE_ASM must be 0 or 1
#endif
/* Derived selection: a target match AND explicit opt-in AND the required ABI.
 * Unknown architectures, disabled ASM and unsupported cores all use C. */
#ifdef SPEEX_NB3_USE_AVR_ASM
#error Set SPEEX_NB3_ARCH and SPEEX_NB3_ENABLE_ASM instead of the internal selector
#endif
#if SPEEX_NB3_ARCH == SPEEX_NB3_ARCH_AVR && SPEEX_NB3_ENABLE_ASM && \
    defined(__AVR__) && defined(__AVR_HAVE_MUL__) && !defined(__AVR_TINY__) && \
    defined(__GNUC__) && !defined(__clang__)
#define SPEEX_NB3_USE_AVR_ASM 1
#else
#define SPEEX_NB3_USE_AVR_ASM 0
#endif

/* Bounds tracking is useful on a host, but optional on freestanding targets. */
#ifndef SPEEX_NB3_CHECK_SCRATCH
#ifdef __AVR__
#define SPEEX_NB3_CHECK_SCRATCH 0
#else
#define SPEEX_NB3_CHECK_SCRATCH 1
#endif
#endif

#if defined(__GNUC__) || defined(__clang__)
#define SPEEX_NB3_NOINLINE __attribute__((noinline))
#define SPEEX_NB3_ALWAYS_INLINE inline __attribute__((always_inline))
#define SPEEX_NB3_CONST __attribute__((const))
#else
#define SPEEX_NB3_NOINLINE
#define SPEEX_NB3_ALWAYS_INLINE inline
#define SPEEX_NB3_CONST
#endif
#if defined(__AVR__) && defined(__GNUC__) && !defined(__clang__)
#define SPEEX_NB3_HOT __attribute__((optimize("O3")))
#define SPEEX_NB3_STAGE SPEEX_NB3_NOINLINE __attribute__((noclone,optimize("O3")))
#define SPEEX_NB3_STAGE_O2 SPEEX_NB3_NOINLINE __attribute__((noclone,optimize("O2")))
#else
#define SPEEX_NB3_HOT
#define SPEEX_NB3_STAGE SPEEX_NB3_NOINLINE
#define SPEEX_NB3_STAGE_O2 SPEEX_NB3_NOINLINE
#endif

/* Speex fixed point requires these integer representations and signed shifts.
 * Also compile with wrapping signed arithmetic and relaxed aliasing, e.g.
 * -fwrapv -fno-strict-aliasing on GCC/Clang (see PORTING.md). */
_Static_assert(CHAR_BIT == 8 && sizeof(int16_t) == 2 && sizeof(int32_t) == 4,
               "NB3 requires 8-bit bytes and exact 16/32-bit integers");
_Static_assert(INT16_MIN == -32768 && INT32_MIN == (-2147483647 - 1),
               "NB3 requires two's-complement integers");
_Static_assert((-2 >> 1) == -1, "NB3 requires arithmetic signed right shift");
#endif
