#ifndef MICROMUSIC_DEVICE_CLOCK_H
#define MICROMUSIC_DEVICE_CLOCK_H
#include <stdint.h>

/* floor((a*b+carry)/divisor), plus remainder. Pure integer implementation for
 * freestanding wasm32, where unsigned __int128 is unavailable. The common
 * short-span path uses only native64-bit multiplication/division. */
static inline int device_clock_ratio(uint64_t a,uint64_t b,uint64_t carry,
 uint64_t divisor,uint64_t *quotient,uint64_t *remainder) {
 if (!divisor) return 0;
 if (!b || a<=(UINT64_MAX-carry)/b) {
  uint64_t n=a*b+carry;
  *quotient=n/divisor; *remainder=n%divisor; return 1;
 }
 /* Long sample/frame counters commonly reduce to a small remainder. Avoid
  * wide division when quotient/remainder decomposition fits native64 bits. */
 uint64_t whole=a/divisor,tail=a%divisor;
 if (tail<=(UINT64_MAX-carry)/b) {
  if (whole>UINT64_MAX/b) return 0;
  uint64_t n=tail*b+carry,q=whole*b,extra=n/divisor;
  if (extra>UINT64_MAX-q) return 0;
  *quotient=q+extra; *remainder=n%divisor; return 1;
 }
 uint64_t a0=(uint32_t)a,a1=a>>32,b0=(uint32_t)b,b1=b>>32;
 uint64_t p=a0*b0,t=a1*b0+(p>>32),middle=(uint32_t)t;
 uint64_t high=a1*b1+(t>>32);
 middle+=a0*b1; high+=middle>>32;
 uint64_t low=(middle<<32)|(uint32_t)p,old=low;
 low+=carry; high+=low<old;
 if (high>=divisor) return 0;
 uint64_t q=0,r=high;
 for (unsigned bit=64;bit--;) {
  uint64_t overflow=r>>63;
  r=(r<<1)|((low>>bit)&1);
  if (overflow || r>=divisor) { r-=divisor; q|=(uint64_t)1<<bit; }
 }
 *quotient=q; *remainder=r; return 1;
}

/* ceil((units*denominator-phase)/rate). Phase is an already elapsed fraction
 * in [0,denominator); subtraction precedes the final upward rounding. */
static inline int device_clock_delay(uint64_t units,uint64_t denominator,
 uint64_t rate,uint64_t phase,uint64_t *ticks) {
 if (!rate || !denominator || phase>=denominator) return 0;
 if (!units) { *ticks=0; return 1; }
 uint64_t q,r;
 if (!device_clock_ratio(units,denominator,0,rate,&q,&r)) return 0;
 uint64_t whole=phase/rate,tail=phase%rate;
 if (q<whole || (q==whole && r<tail)) return 0;
 q-=whole;
 if (r<tail) { --q; r+=rate; }
 r-=tail;
 if (r && q==UINT64_MAX) return 0;
 *ticks=q+(r!=0); return 1;
}
#endif
