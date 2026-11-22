#include "Lpx4HybridCore.h"
#include "Lpx4Math.h"
#if LPX4_FLOAT_SYNTHESIS
#if LPX4_ENABLE_ASM
#error Floating synthesis requires C arithmetic, including platform header selection
#endif
#include "Lpx4Float.h"
#endif
#include <stddef.h>
#include <string.h>
#ifdef LPX4_FIXED_SPEECH_FLAGS
#if !LPX4_COMPACT_ONLY
#error Fixed speech flags require compact-only decoding
#endif
#define LPX4_SPEECH_FLAGS LPX4_FIXED_SPEECH_FLAGS
#else
#define LPX4_SPEECH_FLAGS speechProfile_
#endif
// Compile-time amplitude calibration: same compressed bits, same decoder path.
#ifndef LPX4_PWM_GAIN
#define LPX4_PWM_GAIN 130
#endif
#ifndef LPX4_PWM_ROUND
#define LPX4_PWM_ROUND 1
#endif
#if LPX4_PWM_GAIN < 120 || LPX4_PWM_GAIN > 136
#error LPX4_PWM_GAIN out of tested bounds
#endif
// Optional simple excitation paths:1 raw/zero,2 exhausted sparse,4 cached
// zero-delta pitch Rice k0. Zero retains the complete reference decodeCode.
#ifndef LPX4_FAST_EXCITATION
#define LPX4_FAST_EXCITATION 7
#endif
#if LPX4_FAST_EXCITATION < 0 || (LPX4_FAST_EXCITATION & ~7)
#error Unsupported LPX4_FAST_EXCITATION
#endif
#if LPX4_COMPACT_ONLY && LPX4_COMPACT_VERSION == 9 && LPX4_USE_AVR_NOMUL_ASM && !defined(LPX4_FIXED_SPEECH_FLAGS)
#define LPX4_AVR25_V9_RUNTIME 1
#else
#define LPX4_AVR25_V9_RUNTIME 0
#endif
// Both AVR backends can use the universal v9 ROM player's packet reader.
#if LPX4_AVR25_V9_RUNTIME || (LPX4_COMPACT_ONLY && LPX4_COMPACT_VERSION == 9 && \
    LPX4_USE_AVR_ASM && LPX4_ROM_POINTER && !LPX4_ENABLE_INPUT_CALLBACK && \
    !defined(LPX4_ENABLE_PCM16) && !defined(LPX4_FIXED_SPEECH_FLAGS))
#define LPX4_AVR_V9_PACKETS 1
#else
#define LPX4_AVR_V9_PACKETS 0
#endif
// 0 keeps the reference predictor, bit1 narrows the proven result,
// bit2 bypasses zero history, bit4 additionally bypasses zero gain.
#ifndef LPX4_FAST_PITCH
#define LPX4_FAST_PITCH 3
#endif
#if LPX4_FAST_PITCH < 0 || (LPX4_FAST_PITCH & ~7) || (LPX4_FAST_PITCH && !(LPX4_FAST_PITCH&1))
#error Unsupported LPX4_FAST_PITCH
#endif
#if LPX4_AVR_V9_PACKETS && LPX4_USE_AVR_ASM && LPX4_PLAYER_PITCH_PAGE && LPX4_FAST_PITCH==3 && LPX4_EXCITATION_Q4 && !defined(LPX3_Q_DIAG) && !defined(LPX4_FIXED_PRE_Q14) && !defined(LPX4_FIXED_BRIGHT_Q14)
#define LPX4_AVR5_SAMPLE_LEAF 1
#else
#define LPX4_AVR5_SAMPLE_LEAF 0
#endif
#define LPX4_AVR_V9_HEADER_COPY (LPX4_V9_ROM_HEADER_LAYOUT && LPX4_AVR_V9_PACKETS)
#if LPX4_USE_AVR_ASM && LPX4_MEMORY_PROFILE == LPX4_MEMORY_PROFILE_SRAM512 && !defined(LPX4_FIXED_SPEECH_FLAGS)
#define LPX4_USE_AVR5_POLYNOMIAL_MUL 1
#else
#define LPX4_USE_AVR5_POLYNOMIAL_MUL 0
#endif
#define LPX4_POLY24_WORKSPACE \
    (LPX4_AVR25_V9_RUNTIME || (LPX4_USE_AVR5_POLYNOMIAL_MUL && LPX4_COMPACT_VERSION==9))
#if LPX4_AVR25_V9_RUNTIME && !defined(LPX4_FIXED_PRE_Q14) && !defined(LPX4_FIXED_BRIGHT_Q14)
#define LPX4_AVR25_V9_PREPARED_ATTENUATION 1
#else
#define LPX4_AVR25_V9_PREPARED_ATTENUATION 0
#endif

static inline __attribute__((always_inline)) int16_t limitBrightnessOutput(int16_t value){
#if (LPX4_AVR25_V9_RUNTIME || (LPX4_USE_AVR_ASM && LPX4_COMPACT_VERSION==9)) && \
    !defined(LPX4_ENABLE_PCM16) && LPX4_PWM_ROUND && LPX4_PWM_GAIN>=128 && LPX4_PWM_GAIN<=255
    // The rounded PWM rails are reached at or before the Q14 limits.
    return value;
#else
    return lpx4ClipQ14(value);
#endif
}

#ifdef __AVR__
#include <avr/pgmspace.h>
#define LP_READ_U16(ptr) pgm_read_word((ptr))
#define LP_READ_U8(ptr) pgm_read_byte((ptr))
#define LP_PROGMEM PROGMEM
#else
#define LP_READ_U16(ptr) (*(ptr))
#define LP_READ_U8(ptr) (*(ptr))
#define LP_PROGMEM
#endif
// Preserve signed division's truncation toward zero without AVR libgcc's
// generic 32-bit divide at -Os. All callers use constant powers of two.
static inline __attribute__((always_inline)) int32_t truncShift(int32_t v,uint8_t bits){
    return (v+(v<0?((1L<<bits)-1):0))>>bits;
}

// The private converter uses a custom register contract only in the
// universal Tiny88 ROM profile. All other builds keep the C++ converter.
#if LPX4_AVR25_V9_RUNTIME && LPX4_TINY_ANCHOR_PHASE && !defined(LPX3_BANDWIDTH_EXPAND_Q14) && \
    !defined(LPX3_COST_INSTRUMENT) && \
    defined(LPX25_IRQ_SAMPLE_REGISTER) && defined(LPX25_IRQ_SREG_REGISTER) && \
    LPX25_IRQ_SAMPLE_REGISTER==10 && LPX25_IRQ_SREG_REGISTER==11
#define LPX4_AVR25_LSF_ASM 1
#else
#define LPX4_AVR25_LSF_ASM 0
#endif

static const uint8_t LP_PROGMEM bitMasks[9]={0,1,3,7,15,31,63,127,255};
#if LPX4_COMPACT_VERSION == 9
// High coordinates of a 20x20 pulse pair. Low two bits per position are raw.
// The 5x5 index uses five bits; the full pair still occupies exactly nine.
static constexpr uint8_t packPulseHigh(uint8_t code){
#if LPX4_AVR_V9_PACKETS
    // The upper coordinate's bits land in positions 2..4 after SWAP.
    return (code%5)*4 | (((code/5)&3)<<6) | (code/5>>2);
#else
    return (code%5)*4 | ((code/5)<<5);
#endif
}
static const uint8_t LP_PROGMEM pulseHigh[25]={
 packPulseHigh(0),packPulseHigh(1),packPulseHigh(2),packPulseHigh(3),packPulseHigh(4),
 packPulseHigh(5),packPulseHigh(6),packPulseHigh(7),packPulseHigh(8),packPulseHigh(9),
 packPulseHigh(10),packPulseHigh(11),packPulseHigh(12),packPulseHigh(13),packPulseHigh(14),
 packPulseHigh(15),packPulseHigh(16),packPulseHigh(17),packPulseHigh(18),packPulseHigh(19),
 packPulseHigh(20),packPulseHigh(21),packPulseHigh(22),packPulseHigh(23),packPulseHigh(24)
};
static inline uint8_t secondPulseHigh(uint8_t packed){
#if LPX4_AVR_V9_PACKETS
    packed=(uint8_t)((packed>>4)|(packed<<4));
#else
    packed>>=3;
#endif
    return packed&28;
}
#endif


// Exact differences of cos_table.inc, not an approximation. Every16th
// half-wave node and its positive drop are retained. A nibble stores the
// next drop minus the current drop plus1 (range0..4); low nibble first.
// Reconstruct at most15 intervening nodes, keeping the drop in0..101.
static const uint16_t LP_PROGMEM cosineCheckpoints[8]={
 8192,8035,7568,6811,5793,4551,3135,1598
};
static const uint8_t LP_PROGMEM cosineSlope[8]={1,21,39,56,72,84,93,99};
static const uint8_t LP_PROGMEM cosineBend[64]={
 65,33,35,50,34,34,19,51,49,34,34,35,65,33,35,34,
 34,19,19,35,34,50,33,19,50,49,33,50,33,34,34,49,
 49,17,35,33,34,33,34,33,49,48,33,33,18,49,32,18,
 18,33,33,17,18,2,18,18,48,32,32,17,33,16,2,18
};
#if LPX4_COMPACT_ONLY
// Compact speech transmits a five-bit scale, originalStep[index*8].
#if LPX4_AVR_V9_PACKETS && LPX4_EXCITATION_Q4
#if LPX4_USE_AVR_ASM
__attribute__((noinline))
#endif
static uint16_t scaleStep(uint8_t header){
 // The scale is in the low five bits of the scale/gain byte.
 // The two mantissas are entries 0 and 8 of the original scale grid.
 // Shift into Q4, then round the step to an integer in those units.
 uint16_t scaled=(header&1)?5931:4194;
 uint8_t group=header;
 __asm__(
#if LPX4_USE_AVR_ASM
     "lsr %1\n\tandi %1,15\n\tsubi %1,3\n\tbrcs 5f\n\tsubi %1,9\n\tbreq 4f\n\tbrpl 3f\n\t"
#else
     "lsr %1\n\tandi %1,15\n\tsubi %1,12\n\tbreq 4f\n\tbrpl 3f\n\t"
#endif
     "1: lsr %B0\n\tror %A0\n\tinc %1\n\tbrne 1b\n\trjmp 4f\n\t"
#if LPX4_USE_AVR_ASM
     "3: lsl %A0\n\trol %B0\n\tdec %1\n\tbrne 3b\n\trjmp 4f\n\t"
     "5: clr %A0\n\tclr %B0\n\t4:"
#else
     "3: lsl %A0\n\trol %B0\n\tdec %1\n\tbrne 3b\n\t4:"
#endif
     : "+&w"(scaled),"+d"(group) : : "cc");
 return (scaled+8)&0xfff0;
}
#else
static const uint16_t LP_PROGMEM scaleValues[32]={
 0,0,0,0,0,0,1,1,1,1,2,3,4,6,8,12,
 16,23,33,46,66,93,131,185,262,371,524,741,1049,1483,2097,2966
};
static uint16_t scaleStep(uint8_t index){return LP_READ_U16(&scaleValues[index]);}
#endif
#else
static const uint16_t LP_PROGMEM scaleMantissa[16]={
 4194,4380,4573,4776,4987,5208,5439,5680,
 5931,6194,6468,6754,7053,7366,7692,8032
};
// Exact integer reconstruction of all 256 original scale entries (0..4016).
// Decode once per 80-sample block, including zero aliases; no floating point.
static uint16_t scaleStep(uint8_t index){
 const uint16_t mantissa=LP_READ_U16(&scaleMantissa[index&15]);
 return ((mantissa>>(15-(index>>4)))+1)>>1;
}
#endif
// Adjacent cosine nodes share one reflection. The reflected interval starts
// at -hi and has the same hi-lo slope, so negative floor rounding is exact.
// norm is Q12 in 0..4095; adjacent nodes differ by at most 101.
static inline __attribute__((always_inline)) int16_t cosineInterpolate(uint16_t norm){
 uint8_t index=(uint8_t)(norm>>4);
 const uint8_t fraction=(uint8_t)(norm&15);
 const bool negative=index>=128;
 if(negative)index=(uint8_t)(255-index);
 const uint8_t group=index>>4;
 int16_t lo=LP_READ_U16(&cosineCheckpoints[group]);
 uint8_t drop=LP_READ_U8(&cosineSlope[group]);
 for(uint8_t j=group<<4;j<index;j++){
  lo-=drop;
  const uint8_t pair=LP_READ_U8(&cosineBend[j>>1]);
  drop+=((j&1)?(pair>>4):(pair&15))-1;
 }
 const int16_t hi=lo-drop;
 // floor(-drop*f/16) == -ceil(drop*f/16); product is at most1515.
 const uint16_t loss=((uint16_t)drop*fraction+15)>>4;
 return (int16_t)((negative?-hi:lo)-(int16_t)loss);
}
#if LPX4_COMPACT_ONLY && LPX3_LPC_SEGMENTS != 4
#if LPX4_AVR25_LSF_ASM || (LPX4_USE_AVR_ASM && LPX4_AVR_V9_PACKETS && LPX4_POLY24_WORKSPACE && LPX3_LPC_SEGMENTS==2)
#define LPX4_COSINE_OMITS_ZERO 1
#else
#define LPX4_COSINE_OMITS_ZERO 0
#endif
// Exact cos_table.inc nodes0,2,...128; existing oracle tables stay unchanged.
#if LPX4_MEMORY_PROFILE == LPX4_MEMORY_PROFILE_SRAM512 && defined(LPX4_FIXED_SPEECH_FLAGS) && !(LPX4_SPEECH_FLAGS&2)
// Pinned P4 and segment1/2 produce even half-grid indices. Reflection about
// 64 preserves that parity: retain only the 33 actually reachable entries.
static const uint16_t LP_PROGMEM cosineEven[33]={
 8192,8182,8153,8103,8035,7946,7839,7713,
 7568,7405,7225,7027,6811,6580,6333,6070,
 5793,5501,5197,4880,4551,4212,3862,3503,
 3135,2760,2378,1990,1598,1202,803,402,0
};
#else
#if LPX4_AVR25_LSF_ASM
// Parsed one-based bins yield nodes 1..127 (P4: 2..126). Reflection
// reads entries 1..64, so only this private ASM table omits node zero.
#define LPX4_CONVERT_TABLE_SIZE 64
#define LPX4_CONVERT_TABLE_NAME __asm__("lpx4_tiny_cosine_even") __attribute__((used))
#else
#define LPX4_CONVERT_TABLE_NAME
#define LPX4_CONVERT_TABLE_SIZE (65-LPX4_COSINE_OMITS_ZERO)
#endif
static const uint16_t LP_PROGMEM cosineEven[LPX4_CONVERT_TABLE_SIZE] LPX4_CONVERT_TABLE_NAME={
#if !LPX4_COSINE_OMITS_ZERO
 8192,
#endif
 8190,8182,8170,8153,8130,8103,8071,
 8035,7993,7946,7895,7839,7779,7713,7643,
 7568,7489,7405,7317,7225,7128,7027,6921,
 6811,6698,6580,6458,6333,6203,6070,5933,
 5793,5649,5501,5351,5197,5040,4880,4717,
 4551,4383,4212,4038,3862,3683,3503,3320,
 3135,2948,2760,2570,2378,2185,1990,1795,
 1598,1401,1202,1003,803,603,402,201,
 0
};
#undef LPX4_CONVERT_TABLE_NAME
#undef LPX4_CONVERT_TABLE_SIZE
#endif
#if !LPX4_AVR25_LSF_ASM
// V5 centered5/6bit spectra with segments1/2 reach only even cosine
// nodes: the caller supplies the exact index into this half-grid.
static inline __attribute__((always_inline)) int16_t cosineEvenNode(uint8_t index){
 const bool negative=index>64;
 if(negative)index=128-index;
#if LPX4_MEMORY_PROFILE == LPX4_MEMORY_PROFILE_SRAM512 && defined(LPX4_FIXED_SPEECH_FLAGS) && !(LPX4_SPEECH_FLAGS&2)
 index>>=1;
#endif
 int16_t value=LP_READ_U16(&cosineEven[index-LPX4_COSINE_OMITS_ZERO]);
 return negative?-value:value;
}
#if LPX4_POLY24_WORKSPACE && LPX4_COMPACT_VERSION==9
static inline __attribute__((always_inline)) int16_t lpcCosineFactor(uint8_t node){
 // The factor is -cos(node). Count backwards from the zero at node 64.
 // T holds the sign of node-64 while Z reads the reflected magnitude.
 const uint16_t* cursor=&cosineEven[64-LPX4_COSINE_OMITS_ZERO];
 int16_t value;
 __asm__(
     "subi %1,64\n\tbst %1,7\n\tbrtc 1f\n\tneg %1\n\t"
     "1: lsl %1\n\tsub %A2,%1\n\tsbc %B2,__zero_reg__\n\t"
     "lpm %A0,Z+\n\tlpm %B0,Z\n\t"
     "brtc 2f\n\tcom %B0\n\tneg %A0\n\tsbci %B0,255\n\t2:"
     : "=&d"(value),"+&d"(node),"+z"(cursor) : : "cc","memory");
 return value;
}
#endif
#endif // The private converter performs its own bounded lookup.
#undef LPX4_COSINE_OMITS_ZERO
#endif



#if LPX4_PLAYER_PITCH_PAGE
int8_t Lpx4HybridCore::ringQ_[256] __attribute__((section(".bss"),aligned(256),used));
#endif

#if LPX4_PLAYER_PITCH_PAGE && (LPX4_USE_AVR_NOMUL_ASM || LPX4_USE_AVR_ASM)
template<class Byte>
static inline Byte* pitchRingAddress(Byte* ring,uint8_t offset){
    // The offset replaces the zero low address byte. Keep a relocation for
    // the aligned array so link-time garbage collection retains its storage.
    Byte* address;
    __asm__("mov %A0,%1\n\tldi %B0,hi8(%2)"
#if LPX4_USE_AVR_NOMUL_ASM
            : "=&z"(address)
#else
            : "=&d"(address)
#endif
            : "r"(offset),"i"(ring));
    return address;
}
#define LPX4_PITCH_RING_ADDRESS(ring,offset) pitchRingAddress((ring),(offset))
#define LPX4_PITCH_RING_SAMPLE(ring,offset) (*LPX4_PITCH_RING_ADDRESS((ring),(offset)))
#else
#define LPX4_PITCH_RING_ADDRESS(ring,offset) ((ring)+(offset))
#define LPX4_PITCH_RING_SAMPLE(ring,offset) ((ring)[(offset)])
#endif

Lpx4HybridCore::Lpx4HybridCore(): data_(0),
#if LPX4_V9_ROM_HEADER_LAYOUT
 sampleRate_(0),sampleCount_(0),preQ14_(0),brightQ14_(0),bytes_(0),remaining_(0)
#else
 bytes_(0),
#if !LPX4_ROM_POINTER
 cursor_(0),
#endif
 sampleCount_(0),remaining_(0),sampleRate_(0)
#if LPX4_MEMORY_PROFILE != LPX4_MEMORY_PROFILE_SRAM512 || !defined(LPX4_FIXED_PRE_Q14)
 ,preQ14_(0)
#endif
#if LPX4_MEMORY_PROFILE != LPX4_MEMORY_PROFILE_SRAM512 || !defined(LPX4_FIXED_BRIGHT_Q14)
 ,brightQ14_(0)
#endif
#endif
 {
#if LPX4_ENABLE_INPUT_CALLBACK
 inputReader_=0;inputContext_=0;
#endif
#ifdef __AVR__
 static_assert(offsetof(Lpx4HybridCore,error_)+3<64,"Hot state exceeds AVR short displacement");
 static_assert(offsetof(Lpx4HybridCore,error_)<64,"Error flag must retain short displacement");
#endif
 resetState();
}
// Shared per-stream parser and synthesis reset. Callers retain input, public
// stream metadata, and remaining-count initialization, including failed begin().
void Lpx4HybridCore::resetState(){
 // The transient scalar fields and zeroed history/spectrum arrays form one
 // contiguous span. Keep input, public metadata and callback ownership outside
 // it; LPC anchors/workspace are populated before use and need no clearing.
 const size_t first=offsetof(Lpx4HybridCore,blockStep_);
 const size_t end=offsetof(Lpx4HybridCore,cur_)+sizeof(cur_);
 memset(reinterpret_cast<uint8_t*>(this)+first,0,end-first);
#if LPX4_PLAYER_PITCH_PAGE
 memset(ringQ_,0,sizeof(ringQ_));
#endif
#ifdef LPX3_COST_INSTRUMENT
 lsfConverts_=bitCalls_=romByteCalls_=0;
#endif
}
int16_t Lpx4HybridCore::clamp(int32_t n,int16_t low,int16_t high){
 return n<low?low:(n>high?high:(int16_t)n);
}
// Bounded ROM access and container setup.
uint8_t Lpx4HybridCore::readByte(){
#ifdef LPX3_COST_INSTRUMENT
 ++romByteCalls_;
#endif
#if !(LPX4_AVR_V9_PACKETS && LPX4_ROM_POINTER && !LPX4_ENABLE_INPUT_CALLBACK && !defined(LPX4_ENABLE_PCM16) && !defined(LPX3_COST_INSTRUMENT))
 // Other backends can fail for reasons besides exhausting the ROM span.
 if(error_)return 0;
#else
 // ROM parsing starts with a clear error. Exhaustion leaves bytes_ at
 // zero. Other errors return to the caller before requesting more bytes.
#endif
#if LPX4_ENABLE_INPUT_CALLBACK
 if(inputReader_){
#if LPX4_ROM_POINTER
  if(!bytes_){error_=END_OF_ROM;return 0;}
  --bytes_;
#else
  if(cursor_>=bytes_){error_=END_OF_ROM;return 0;}
  ++cursor_;
#endif
  const int16_t value=inputReader_(inputContext_);
  if(value<0 || value>255){error_=END_OF_ROM;return 0;}
  return (uint8_t)value;
 }
#endif
#if LPX4_ROM_POINTER
 if(!bytes_){error_=END_OF_ROM;return 0;}
 --bytes_;
#if LPX4_AVR_V9_PACKETS
 // Advance the bounded ROM cursor with the byte read.
 const uint8_t* next=data_;
 uint8_t value;
 __asm__("lpm %0,Z+" : "=&r"(value),"+z"(next) :: "memory");
 data_=next;
 return value;
#else
 return LP_READ_U8(data_++);
#endif
#else
 if(cursor_>=bytes_){error_=END_OF_ROM;return 0;}
 return LP_READ_U8(data_+cursor_++);
#endif
}
uint16_t Lpx4HybridCore::read16(){
 const uint16_t low=readByte();return (uint16_t)(low | (uint16_t)readByte()<<8);
}
uint32_t Lpx4HybridCore::read32(){
 const uint32_t low=read16();return low|((uint32_t)read16()<<16);
}
#if LPX4_ENABLE_INPUT_CALLBACK
bool Lpx4HybridCore::begin(const uint8_t* input,uint16_t size){
 inputReader_=0;inputContext_=0;data_=input;
 return beginSource(size);
}
bool Lpx4HybridCore::beginStream(ReadByte reader,void* context,uint16_t size){
 inputReader_=reader;inputContext_=context;data_=0;
 return beginSource(size);
}
#if LPX4_ENABLE_WIDE_V9
bool Lpx4HybridCore::beginWideV9(const uint8_t* input,uint32_t size){
 inputReader_=0;inputContext_=0;data_=input;
 return beginSource(size);
}
#endif
bool Lpx4HybridCore::beginSource(Lpx4InputSize size){
 bytes_=size;
#else
#if LPX4_V9_ROM_HEADER_LAYOUT
bool Lpx4HybridCore::begin(const uint8_t* input,uint16_t size){
 return beginRom(input,size,true);
}
#if LPX4_USE_AVR_ASM
// Keep header validation outside the foreground decode loop's register frame.
__attribute__((noinline))
#endif
bool Lpx4HybridCore::beginRom(const uint8_t* input,uint16_t size,bool reset){
#else
#if LPX4_ENABLE_WIDE_V9
bool Lpx4HybridCore::begin(const uint8_t* input,uint16_t size){
 return beginWideV9(input,size);
}
bool Lpx4HybridCore::beginWideV9(const uint8_t* input,uint32_t size){
#else
bool Lpx4HybridCore::begin(const uint8_t* input,uint16_t size){
#endif
#endif
#if !LPX4_AVR_V9_HEADER_COPY
 data_=input;bytes_=size;
#endif
#endif
#if !LPX4_ROM_POINTER
 cursor_=0;
#endif
#if LPX4_V9_ROM_HEADER_LAYOUT
 if(reset){
  remaining_=sampleCount_;
  resetState();
 }
#else
 remaining_=sampleCount_;
 resetState();
#endif
#if LPX4_ENABLE_INPUT_CALLBACK
 if((!data_&&!inputReader_)||size<(LPX4_COMPACT_VERSION==9?13:20)){error_=BAD_HEADER;return false;}
#else
 if(!input||size<(LPX4_COMPACT_VERSION==9?13:20)){error_=BAD_HEADER;return false;}
#endif
#if LPX4_AVR_V9_HEADER_COPY
 if(LP_READ_U16(input)!=0x394c){error_=BAD_HEADER;return false;}
 const uint8_t flags=LP_READ_U8(input+2);
#elif LPX4_COMPACT_VERSION == 9
 if(read16()!=0x394c){error_=BAD_HEADER;return false;}
#if LPX4_ENABLE_WIDE_V9
 const uint8_t wireFlags=readByte();
 const bool wideHeader=(wireFlags&64)!=0;
 const uint8_t flags=wireFlags&~64;
#else
 const uint8_t flags=readByte();
#endif
#else
 if(readByte()!='L'||readByte()!='4'||readByte()!='H'||readByte()!='Y'){
  error_=BAD_HEADER;return false;
 }
 const uint8_t version=readByte(),flags=readByte();
#endif
#ifdef LPX4_FIXED_SPEECH_FLAGS
 if(flags!=LPX4_FIXED_SPEECH_FLAGS){error_=UNSUPPORTED;return false;}
#endif
#if LPX4_COMPACT_ONLY
#if LPX4_COMPACT_VERSION == 9
 // Dense profiles differ by bit 1 and have optional extras in bit 7.
 if(flags!=15 && (flags&0x7d)!=4){
#else
#if LPX4_HAS_SPARSE80
 const bool sparse80=version==8 && flags==15;
 if(!sparse80 &&
#else
 if(
#endif
    (version!=LPX4_COMPACT_VERSION || ((flags&127)!=4 && (flags&127)!=6))){
#endif
  error_=UNSUPPORTED;return false;
 }
 // Raw profile15 keeps bit1 for the six-bit spectrum and bit3 for sparse80.
#if LPX4_MEMORY_PROFILE != LPX4_MEMORY_PROFILE_SRAM512 || !defined(LPX4_FIXED_SPEECH_FLAGS)
 speechProfile_=flags;
#endif
#else
#if LPX4_ENABLE_SPEECH_COMPACT
 if(version==5 && ((flags&127)==4 || (flags&127)==6)){
  LPX4_SPEECH_FLAGS=flags&127;speechCompact_=1|(flags&128);
 }else
#endif
#if LPX4_ENABLE_SPEECH
 if(version==4 && (flags==4 || flags==6))speechProfile_=flags;
 else
#endif
 {
#if LPX4_V3_FEATURES
 if(version==3 && (flags&3)==3 && !(flags&~(3|LPX4_V3_FEATURES)))formatFeatures_=flags&124;
 else if(version!=2||flags!=3){error_=UNSUPPORTED;return false;}
#else
 if(version!=2||flags!=3){error_=UNSUPPORTED;return false;}
#endif
 }
#endif
#if LPX4_AVR_V9_HEADER_COPY
 // The complete header is in bounds. Copy the five little-endian words,
 // including the payload length, and keep the advanced Flash pointer.
 constexpr size_t first=offsetof(Lpx4HybridCore,sampleRate_);
 static_assert(offsetof(Lpx4HybridCore,sampleCount_)==first+2 &&
               offsetof(Lpx4HybridCore,preQ14_)==first+4 &&
               offsetof(Lpx4HybridCore,brightQ14_)==first+6 &&
               offsetof(Lpx4HybridCore,bytes_)==first+8,
               "v9 fields must match the wire order");
 uint8_t* destination=reinterpret_cast<uint8_t*>(this)+first;
 const uint8_t* cursor=input+3;
 uint8_t count=10,value;
 __asm__ volatile("1: lpm %3,Z+\n\tst %a0+,%3\n\tdec %2\n\tbrne 1b"
    : "+&x"(destination),"+&z"(cursor),"+&r"(count),"=&r"(value) : : "cc","memory");
 data_=cursor;
#else
 sampleRate_=read16();
#if LPX4_COMPACT_VERSION == 9
#if LPX4_ENABLE_WIDE_V9
 sampleCount_=wideHeader?read32():read16();
#else
 sampleCount_=read16();
#endif
#else
 sampleCount_=read32();
#endif
#if LPX4_MEMORY_PROFILE == LPX4_MEMORY_PROFILE_SRAM512 && defined(LPX4_FIXED_PRE_Q14)
 const uint16_t preQ14_=read16();
#else
 preQ14_=read16();
#endif
#if LPX4_MEMORY_PROFILE == LPX4_MEMORY_PROFILE_SRAM512 && defined(LPX4_FIXED_BRIGHT_Q14)
 const uint16_t brightQ14_=read16();
#else
 brightQ14_=read16();
#endif
#endif
 remaining_=sampleCount_;
#if LPX4_BATCHED_REMAINING
 subEnd_=remaining_<20?(uint8_t)remaining_:20;
#endif
#if LPX4_COMPACT_VERSION != 9
 const uint16_t frames=read16(),blocks=read16();
#endif
#if LPX4_COMPACT_ONLY
#if LPX4_COMPACT_VERSION == 9
 const bool geometry=true;
#else
 const bool geometry=frames==320 && blocks==
#if LPX4_HAS_SPARSE80
 ((LPX4_SPEECH_FLAGS&8)?320:160);
#else
 160;
#endif
#endif
#if LPX4_AVR_V9_HEADER_COPY
 const uint16_t payload=bytes_;
#else
#if LPX4_ENABLE_WIDE_V9
 const uint32_t payload=wideHeader?read32():read16();
#else
 const uint16_t payload=read16();
#endif
#endif
#if LPX4_ENABLE_WIDE_V9
 const uint8_t headerBytes=wideHeader?17:13;
 if(!sampleCount_ || (!wideHeader&&(sampleCount_>64000||size>65535)) ||
    size<headerBytes || payload!=size-headerBytes){
#else
 const uint8_t headerBytes=LPX4_COMPACT_VERSION==9?13:22;
 // Subtract the header from the bounded input span; no untrusted wide sum.
 if(sampleCount_>64000 || !sampleCount_ || (size<headerBytes || payload!=(uint16_t)(size-headerBytes))){
#endif
  error_=BAD_HEADER;return false;
 }
#else
 bool geometry=frames==160 && blocks==80;
#if LPX4_ENABLE_SPEECH
 if(LPX4_SPEECH_FLAGS){
  geometry=frames==320 && blocks==160;
  // Full final packet is mandatory, even for a partial sample tail. Bound
  // the count before addition/multiplication; reject truncation at begin().
  bool complete;
#if LPX4_ENABLE_SPEECH_COMPACT
  if(speechCompact_){const uint16_t payload=read16();complete=size>=22 && payload==(uint16_t)(size-22);}
  else
#endif
  // Accepted counts are <=64000: count+319 and the byte length fit uint16.
  // Larger counts are still rejected by the full-width guard below.
  complete=size==(uint16_t)(20+(((uint16_t)sampleCount_+319u)/320u)*(LPX4_SPEECH_FLAGS==4?20:30));
  if(sampleCount_>64000 || !sampleCount_ || !complete){
   error_=BAD_HEADER;return false;
  }
 }
#endif
#endif
#ifdef LPX4_FIXED_PRE_Q14
 if(preQ14_!=LPX4_FIXED_PRE_Q14){error_=UNSUPPORTED;return false;}
#endif
#ifdef LPX4_FIXED_BRIGHT_Q14
 if(brightQ14_!=LPX4_FIXED_BRIGHT_Q14){error_=UNSUPPORTED;return false;}
#endif
#if LPX4_SAMPLE_RATE
 if((!LPX4_AVR_V9_HEADER_COPY && error_)||sampleRate_!=LPX4_SAMPLE_RATE||!sampleCount_||!geometry||
#elif LPX4_EXTENDED_SAMPLE_RATES && LPX4_COMPACT_VERSION==9
 const bool unsupportedRate=sampleRate_!=8000 && sampleRate_!=12000 && sampleRate_!=16000;
 if((!LPX4_AVR_V9_HEADER_COPY && error_)||unsupportedRate||!sampleCount_||!geometry||
#else
 if((!LPX4_AVR_V9_HEADER_COPY && error_)||sampleRate_!=8000||!sampleCount_||!geometry||
#endif
    preQ14_>16384||brightQ14_>11469){error_=BAD_HEADER;return false;}
#if LPX4_AVR25_V9_PREPARED_ATTENUATION
 preQ14_=lpx4PrepareAttenuationQ14(preQ14_);
 brightQ14_=lpx4PrepareAttenuationQ14(brightQ14_);
#endif
 return true;
}
// LSB-first bit and entropy readers.
// Share cache/refill logic and its single diagnostic call with readBits.
uint8_t Lpx4HybridCore::readOne(){return readBits(1);}

#if !LPX4_COMPACT_ONLY
// Consume the mandatory two-bit Huffman prefix in one cached operation.
// Zero retains the original per-bit path; instrumentation preserves its costs.
#ifndef LPX4_FAST_HUFFMAN3
#define LPX4_FAST_HUFFMAN3 1
#endif
#if LPX4_FAST_HUFFMAN3 != 0 && LPX4_FAST_HUFFMAN3 != 1
#error LPX4_FAST_HUFFMAN3 must be 0 or 1
#endif
int8_t Lpx4HybridCore::readHuffman3(){
#if LPX4_FAST_HUFFMAN3 && !defined(LPX3_COST_INSTRUMENT)
 uint8_t prefix;
 if(bitsLeft_>=2){prefix=bitBuffer_&3;bitBuffer_>>=2;bitsLeft_-=2;}
 else prefix=readBits(2);
 if(prefix==0)return -1;
 if(prefix==1)return 0;
 if(prefix==2)return readOne()?-2:2;
#else
 if(!readOne()){
  if(!readOne())return -1;
  return readOne()?-2:2;
 }
 if(!readOne())return 0;
#endif
 if(readOne())return 1;
 if(!readOne())return 3;
 return readOne()?-3:-4;
}
#endif
#if LPX4_AVR_V9_PACKETS
// The left shift may use zero cached bits; readBits always consumes at
// least one bit from the source byte on the right shift path.
template<bool left>
static inline __attribute__((always_inline)) uint8_t shiftPacketByte(uint8_t value,uint8_t count){
 __asm__(
     ".if %2\n\ttst %1\n\tbreq 2f\n\t.endif\n\t"
     "1:\n\t.if %2\n\tlsl %0\n\t.else\n\tlsr %0\n\t.endif\n\t"
     "dec %1\n\tbrne 1b\n\t2:"
     : "+&r"(value),"+r"(count) : "I"(left) : "cc");
 return value;
}
#endif
uint8_t Lpx4HybridCore::readBits(uint8_t n){
#ifdef LPX3_COST_INSTRUMENT
 ++bitCalls_;
#endif

#if LPX4_AVR_V9_PACKETS && LPX4_V9_ROM_HEADER_LAYOUT && !defined(LPX4_ENABLE_PCM16)
 // Compact v9 calls request 1..8 bits. One ROM byte suffices for a refill.
 uint8_t out,source,remaining,used;
 Lpx4HybridCore* base=this;
 uint8_t lo,hi;
 static_assert(sizeof(data_)==2 && sizeof(bytes_)==2 && sizeof(error_)==1 &&
               offsetof(Lpx4HybridCore,error_)<64 &&
               offsetof(Lpx4HybridCore,bitBuffer_)<64 &&
               offsetof(Lpx4HybridCore,bitsLeft_)<64 &&
               offsetof(Lpx4HybridCore,bytes_)+1<64 &&
               offsetof(Lpx4HybridCore,data_)==0,
               "LPX v9 reader requires AVR short displacements");
 __asm__ volatile(
     // Keep the object in Z while the cached bits suffice.
     "ldd %[rem],Z+%[left]\n\tldd %[src],Z+%[buffer]\n\t"
     "mov %[out],%[src]\n\tmov %[use],%[n]\n\tsub %[rem],%[n]\n\tbrcc 6f\n\t"
     // Subtract from the ROM bound without committing an underflow.
     "ldd %[lo],Z+%[bytes]\n\tldd %[hi],Z+%[bytes_hi]\n\t"
     "subi %[lo],1\n\tsbci %[hi],0\n\tbrcc 2f\n\t"
     "ldi %[lo],%[end_rom]\n\tstd Z+%[error],%[lo]\n\tclr %[src]\n\trjmp 3f\n\t"
     // Borrow X for the leading cursor word and restore the object in Z.
     "2: std Z+%[bytes],%[lo]\n\tstd Z+%[bytes_hi],%[hi]\n\t"
     "movw r26,r30\n\tld r30,X+\n\tld r31,X\n\tlpm %[src],Z+\n\t"
     "st X,r31\n\tst -X,r30\n\tmovw r30,r26\n\t"
     // The borrow path joins the new byte after the old cached bits.
     "3: mov %[lo],%[src]\n\tadd %[use],%[rem]\n\tbreq 5f\n\t"
     "4: lsl %[lo]\n\tdec %[use]\n\tbrne 4b\n\t"
     "5: or %[out],%[lo]\n\tmov %[use],%[rem]\n\tneg %[use]\n\t"
     // Discard the positive bit count and retain the unread part.
     "6: lsr %[src]\n\tdec %[use]\n\tbrne 6b\n\t"
     "andi %[rem],7\n\tstd Z+%[left],%[rem]\n\tstd Z+%[buffer],%[src]\n\t"
     : [out] "=&r"(out),[src] "=&r"(source),[rem] "=&d"(remaining),
       [use] "=&r"(used),[lo] "=&d"(lo),[hi] "=&d"(hi), [obj] "+z"(base)
     : [n] "r"(n),
       [bytes] "I"(offsetof(Lpx4HybridCore,bytes_)),
       [bytes_hi] "I"(offsetof(Lpx4HybridCore,bytes_)+1),
       [left] "I"(offsetof(Lpx4HybridCore,bitsLeft_)),
       [buffer] "I"(offsetof(Lpx4HybridCore,bitBuffer_)),
       [error] "I"(offsetof(Lpx4HybridCore,error_)),
       [end_rom] "M"((uint8_t)END_OF_ROM)
     : "r26","r27","cc","memory");
 return out&LP_READ_U8(&bitMasks[n]);
#elif LPX4_AVR_V9_PACKETS
#if LPX4_USE_AVR_ASM
 uint8_t available=bitsLeft_;
 int8_t remaining=available-n;
#else
 const uint8_t available=bitsLeft_;
 const int8_t remaining=available-n;
#endif
 uint8_t out=bitBuffer_,source=out,used=n;
 if(remaining<0){
  source=readByte();
#if LPX4_USE_AVR_ASM
  // Reload the cache after the AVR5 refill call so its registers need
  // not be saved across the call. The AVR25 refill normally inlines.
  available=bitsLeft_;
  remaining=available-n;
  out=bitBuffer_;
#endif
  used=(uint8_t)-remaining;
  out|=shiftPacketByte<true>(source,available);
 }
 // A refill supplies eight more bits. The low three bits give the
 // remaining count on both paths; mask the field after joining both bytes.
 bitBuffer_=shiftPacketByte<false>(source,used);
 bitsLeft_=remaining&7;
 return out&LP_READ_U8(&bitMasks[n]);
#elif LPX4_COMPACT_ONLY && LPX4_USE_AVR_NOMUL_ASM && !defined(LPX4_FIXED_SPEECH_FLAGS)
 const uint8_t available=bitsLeft_;
 uint8_t source, used, remaining, out;
 if(available>=n){
  source=bitBuffer_;
  used=n;
  remaining=available-n;
  out=source&LP_READ_U8(&bitMasks[used]);
 }else{
  source=readByte();
  used=n-available;
  remaining=8-used;
  out=bitBuffer_|((source&LP_READ_U8(&bitMasks[used]))<<available);
 }
 // The cache is one byte. Use one byte-wide shift loop on both paths.
 while(used--)source>>=1;
 bitBuffer_=source;
 bitsLeft_=remaining;
 return out;
#else
 const uint8_t available=bitsLeft_;
 uint8_t out;
 if(available>=n){
  out=bitBuffer_&LP_READ_U8(&bitMasks[n]);
  bitBuffer_>>=n;bitsLeft_=available-n;
 }else{
  const uint8_t extra=readByte(),need=n-available;
  out=bitBuffer_|((extra&LP_READ_U8(&bitMasks[need]))<<available);
  bitBuffer_=extra>>need;bitsLeft_=8-need;
 }
 return out;
#endif
}
#if LPX4_ENABLE_SPEECH_COMPACT
uint8_t Lpx4HybridCore::readSpeechRice(uint8_t k,uint8_t width){
#if LPX4_COMPACT_ONLY && (LPX4_USE_AVR_NOMUL_ASM || LPX4_AVR_V9_PACKETS) && !defined(LPX4_FIXED_SPEECH_FLAGS)
 // Accumulate high << k as zeros arrive. The eighth zero still selects escape.
#if LPX4_AVR_V9_PACKETS && LPX4_V9_ROM_HEADER_LAYOUT && !defined(LPX4_ENABLE_PCM16)
 // Compact LSF Rice widths leave only k=0, 1, or 2.
 const uint8_t step=k+k+(k==0);
#else
 const uint8_t step=1<<k;
#endif
 uint8_t upper=0;
 for(uint8_t high=0;high<8;++high){
  if(readOne())return upper|(k?readBits(k):0);
  if(error_)return 0;
  upper+=step;
 }
#if LPX4_AVR_V9_PACKETS && LPX4_V9_ROM_HEADER_LAYOUT && !defined(LPX4_ENABLE_PCM16)
 // bits=5+(profile&2)/2, k=bits-4-delta, width=bits+delta.
 // Reconstruct only on escape, avoiding a held width through the prefix.
 return readBits(6+(LPX4_SPEECH_FLAGS&2)-k);
#else
 return readBits(width);
#endif
#else
 uint8_t high=0;
 while(high<8 && !readOne()){
  if(error_)return 0;
  ++high;
 }
 if(high==8)return readBits(width);
 return (high<<k)|(k?readBits(k):0);
#endif
}
#endif
// Container parsing: frame, block, and subframe headers.
bool Lpx4HybridCore::readFrame(){
#if LPX4_LPC2_LSF_OVERLAY
 // The upper anchor is dead until midpoint output replaces it.
 uint8_t* const oldBins=reinterpret_cast<uint8_t*>(lpcAnchors_+10);
#define LPX4_PREVIOUS_BINS oldBins
#else
#define LPX4_PREVIOUS_BINS prev_
#endif
#if !LPX4_COMPACT_ONLY
 for(uint8_t i=0;i<10;i++)LPX4_PREVIOUS_BINS[i]=cur_[i];
#endif
#if LPX4_ENABLE_SPEECH
#if !LPX4_COMPACT_ONLY
 if(LPX4_SPEECH_FLAGS){
#else
 {
#endif
  staticSpectrum_=true;
#if LPX4_AVR25_V9_RUNTIME && LPX4_AVR25_V9_ROM_LAYOUT && !defined(LPX4_ENABLE_PCM16)
  if(subIndex_&8){
   // The second Sparse80 half reuses the spectrum and consumes no header.
   if(LPX4_SPEECH_FLAGS&8)return true;
  }else{
#elif LPX4_AVR25_V9_RUNTIME
  if((LPX4_SPEECH_FLAGS&8) && (subIndex_&8))return true;
  if(!(subIndex_&8)){
#elif LPX4_COMPACT_ONLY
  if(!(subIndex_&8)){
#else
  if(!speechHalf_){
#endif
#if LPX4_COMPACT_ONLY && !LPX4_AVR_V9_PACKETS
   // The second half uses cached LPC; the next first half refreshes prev.
   for(uint8_t i=0;i<10;i++)LPX4_PREVIOUS_BINS[i]=cur_[i];
#endif
#if LPX4_AVR25_V9_RUNTIME
   const uint8_t wide=(LPX4_SPEECH_FLAGS>>1)&1;
   const uint8_t bits=wide+5;
#else
   const uint8_t bits=(LPX4_SPEECH_FLAGS&2)?6:5;
#endif
#if !LPX4_COMPACT_ONLY
   const uint8_t shift=10-bits;
#endif
#if LPX4_ENABLE_SPEECH_COMPACT
#if !LPX4_COMPACT_ONLY
   if(speechCompact_){
#else
   {
#endif
#if LPX4_AVR25_V9_RUNTIME && LPX4_AVR25_V9_ROM_LAYOUT && !defined(LPX4_ENABLE_PCM16)
    const bool haveSpectrum=initializedFrame_;
    if(!readOne()){
     if(!haveSpectrum){error_=CORRUPT_STREAM;return false;}
    }else{
     const bool delta=readOne()!=0;
     if(delta&&!haveSpectrum){error_=CORRUPT_STREAM;return false;}
#else
    if(!readOne()){
     if(!initializedFrame_){error_=CORRUPT_STREAM;return false;}
    }else{
     const bool delta=readOne()!=0;
     if(delta&&!initializedFrame_){error_=CORRUPT_STREAM;return false;}
#endif
     const uint8_t k=bits-4-(uint8_t)delta;
     // AVR25 keeps the same one-based indices in the parser and workspace.
     // Converting a negative delta result to uint8_t puts it above the limit.
#if LPX4_AVR25_V9_RUNTIME
     const uint8_t width=bits+(uint8_t)delta;
#endif
#if LPX4_AVR_V9_PACKETS
     uint8_t last=0;
#else
     int8_t last=-1;
#endif
#if LPX4_AVR25_V9_RUNTIME
     const uint8_t limit=wide?64:32;
#else
     const uint8_t limit=((LPX4_SPEECH_FLAGS&2)+2)<<4;
#endif
     for(uint8_t i=0;i<10;i++){
#if LPX4_AVR25_V9_RUNTIME
      const uint8_t code=readSpeechRice(k,width);
#else
      const uint8_t code=readSpeechRice(k,bits+(delta?1:0));
#endif
      // Compact Rice codes use at most seven bits: delta is -64..63.
#if LPX4_AVR_V9_PACKETS
      const int8_t difference=(code>>1)^-(code&1);
      const uint8_t previous=cur_[i];
      const uint8_t value=delta?previous+difference:last+1+code;
      if(error_)return false;
      if(value<=last || value>limit){error_=CORRUPT_STREAM;return false;}
      // A repeat uses the cached LPC. Save the old LSF only when decoding a
      // new vector, immediately before replacing the corresponding index.
      LPX4_PREVIOUS_BINS[i]=previous;
      if(value!=previous)staticSpectrum_=false;
      cur_[i]=value;last=value;
#else
      const int8_t difference=(code&1)?-(int8_t)((code+1)>>1):(int8_t)(code>>1);
#if LPX4_COMPACT_ONLY
      const int8_t value=delta?(LPX4_PREVIOUS_BINS[i]-1+difference):last+1+code;
#else
      const int8_t value=delta?((LPX4_PREVIOUS_BINS[i]>>shift)+difference):last+1+code;
#endif
      if(error_)return false;
      if(value<=last || (uint8_t)value>=limit){error_=CORRUPT_STREAM;return false;}
#if LPX4_COMPACT_ONLY
      const uint8_t v=value+1;
#else
      const int16_t v=(value<<shift)+(1u<<(shift-1));
#endif
      if(initializedFrame_ && v!=LPX4_PREVIOUS_BINS[i])staticSpectrum_=false;
      cur_[i]=v;last=value;
#endif
     }
    }
   }
#if !LPX4_COMPACT_ONLY
   else
#endif
#endif
#if !LPX4_COMPACT_ONLY
   {
   for(uint8_t i=0;i<10;i++){
    const int16_t v=((uint16_t)readBits(bits)<<shift)+(1u<<(shift-1));
    if(i && v<=cur_[i-1]){error_=CORRUPT_STREAM;return false;}
    if(initializedFrame_ && v!=LPX4_PREVIOUS_BINS[i])staticSpectrum_=false;
    cur_[i]=v;
   }
   if(LPX4_SPEECH_FLAGS==6 && readBits(6)){error_=CORRUPT_STREAM;return false;}
   }
#endif
  }
#if LPX4_AVR_V9_PACKETS
  if(!initializedFrame_){
   staticSpectrum_=true;
   initializedFrame_=true;
  }
#else
  if(!initializedFrame_)for(uint8_t i=0;i<10;i++)LPX4_PREVIOUS_BINS[i]=cur_[i];
  initializedFrame_=true;
#endif
#if LPX4_COMPACT_ONLY && !LPX4_AVR_V9_PACKETS
  subIndex_^=8;
#elif !LPX4_COMPACT_ONLY
  speechHalf_^=1;
#endif
#if LPX4_COMPACT_ONLY
#if LPX4_HAS_SPARSE80 && !LPX4_AVR25_V9_RUNTIME
#if LPX4_AVR_V9_PACKETS
  const bool secondHalf=subIndex_&8;
#else
  const bool secondHalf=!(subIndex_&8);
#endif
  if((LPX4_SPEECH_FLAGS&8) && secondHalf)return !error_;
#endif
#if LPX4_AVR_V9_PACKETS
  // The v9 scale and gain are adjacent LSB-first fields, eight bits total.
  const uint8_t blockHeader=readBits(8);
#else
  const uint8_t blockScale=readBits(5);
#endif
#else
  mode_=6;quantLimit_=32;
  blockScale_=readBits(5)<<3;
#endif
#if LPX4_COMPACT_VERSION == 9
#if LPX4_AVR_V9_PACKETS
#if LPX4_AVR25_V9_RUNTIME && LPX4_EXCITATION_Q4
  blockStep_=scaleStep(blockHeader);
#endif
#if LPX4_AVR5_SAMPLE_LEAF
  // Keep the packed gain in Q8 units for one hardware multiply per sample.
  gain_=blockHeader&224;
#else
  gain_=(blockHeader>>4)&14;
#endif
#else
  gain_=readBits(3)<<1;
#endif
  // At zero gain the lag contributes exactly zero for every history value.
  lag_=gain_?18+readBits(7):18;
#else
  lag_=18+readBits(7);gain_=readBits(3)<<1;
#endif
#if LPX4_AVR_V9_PACKETS && !(LPX4_AVR25_V9_RUNTIME && LPX4_EXCITATION_Q4)
#if LPX4_USE_AVR_ASM && LPX4_EXCITATION_Q4
  blockStep_=scaleStep(blockHeader);
#else
  blockStep_=scaleStep(blockHeader&31);
#endif
#elif !LPX4_AVR_V9_PACKETS
#if LPX4_COMPACT_ONLY
  blockStep_=scaleStep(blockScale);
#else
  blockStep_=scaleStep(blockScale_);
#endif
#endif
#if LPX4_EXCITATION_Q4 && !LPX4_AVR_V9_PACKETS
  blockStep_<<=4;
#endif
  return !error_;
 }
#endif
#if !LPX4_COMPACT_ONLY
 if(!readOne()){
  if(!initializedFrame_){error_=CORRUPT_STREAM;return false;}
  staticSpectrum_=true;
  return !error_;
 }
 int16_t v[10];
 if(!readOne()){
  // LSF10 absolute: 10 * exactly 10 bits (no pad to 13-byte frame).
  for(uint8_t i=0;i<10;i++)v[i]=(int16_t)(readBits(8)|((uint16_t)readBits(2)<<8));
 }else{
  if(!initializedFrame_){error_=CORRUPT_STREAM;return false;}
#if LPX4_V3_FEATURES & 64
  const uint8_t coding=(formatFeatures_&64)?readBits(2):readOne();
#else
  // Preserve the v2 Boolean branch/code generation without optional LSF Rice.
  const bool coding=readOne()!=0;
#endif
  for(uint8_t i=0;i<10;i++){
   int8_t d=0;
   if(coding==1)d=(int8_t)readBits(8);
#if LPX4_V3_FEATURES & 64
   else if(coding>=2){
    const uint8_t k=coding==2?0:2;
    uint8_t high=0;
    while(high<8 && !readOne()){
     if(error_){error_=CORRUPT_STREAM;return false;}++high;
    }
    if(high==8)d=(int8_t)readBits(8);
    else{
     const uint8_t z=(high<<k)|(k?readBits(k):0);
     d=(z&1)?-(int8_t)((z+1)>>1):(int8_t)(z>>1);
    }
   }
#endif
   else {
    uint8_t z=0;
    while(!readOne()){
     if(error_||++z>7){error_=CORRUPT_STREAM;return false;}
    }
    const int8_t hi=(z&1)?-(int8_t)((z+1)>>1):(int8_t)(z>>1);
    const uint8_t lo=readOne()?readBits(5):0;
    d=(int8_t)((int16_t)hi*32+lo);
   }
   v[i]=cur_[i]+d;
  }
 }
 if(error_)return false;
 staticSpectrum_=true;
 for(uint8_t i=0;i<10;i++){
  if(v[i]<0||v[i]>1023){error_=CORRUPT_STREAM;return false;}
  if(initializedFrame_ && v[i]!=LPX4_PREVIOUS_BINS[i])staticSpectrum_=false;
  cur_[i]=v[i];
 }
 if(!initializedFrame_)for(uint8_t i=0;i<10;i++)LPX4_PREVIOUS_BINS[i]=cur_[i];
 initializedFrame_=true;return true;
#endif
#undef LPX4_PREVIOUS_BINS
}
#if !LPX4_COMPACT_ONLY
bool Lpx4HybridCore::readBlock(){
#if LPX4_ENABLE_SPEECH
 if(LPX4_SPEECH_FLAGS)return !error_;
#endif
#if LPX4_V3_FEATURES & 8
 if(!(formatFeatures_&8) || readOne())
#endif
 mode_=readBits(3); // source bit depth, 0 or 2..6
 if(mode_!=0 && (mode_<2 || mode_>6)){error_=CORRUPT_STREAM;return false;}
 quantLimit_=mode_?(1u<<(mode_-1)):0;
#if LPX4_V3_FEATURES & 32
 if((formatFeatures_&32) && !mode_)return !error_;
#endif
#if LPX4_V3_FEATURES & 4
 if((formatFeatures_&4) && !readOne())return !error_;
#endif
 uint8_t q=0;
 while(q<6 && !readOne()){
  if(error_){error_=CORRUPT_STREAM;return false;}++q;
 }
 if(q==6)blockScale_=readBits(8);
 else{
  const uint8_t z=(uint8_t)((q<<4)|readBits(4));
  const int16_t d=(z&1)?-(int16_t)((z+1)>>1):(int16_t)(z>>1);
  const int16_t target=(int16_t)blockScale_+d;
  if(target<0||target>255){error_=CORRUPT_STREAM;return false;}
  blockScale_=(uint8_t)target;
 }
 blockStep_=scaleStep(blockScale_);
#if LPX4_EXCITATION_Q4
 blockStep_<<=4; // 4016*16=64256 fits unsigned16.
#endif
 return !error_;
}
#endif
#if LPX4_ENABLE_SPEECH
// Four encoded positions occupy five sample slots, skipping the middle slot.
// P4 and Sparse80 use the same mapping over different numbers of groups.
static inline uint8_t compactPulsePosition(uint8_t code){
#if LPX4_AVR25_V9_RUNTIME || (LPX4_AVR_V9_PACKETS && LPX4_V9_ROM_HEADER_LAYOUT && !defined(LPX4_ENABLE_PCM16) && LPX4_USE_AVR_ASM)
    // floor((code+2)/4) is code>>2 plus its original bit 1. The second
    // shift leaves that bit in carry, so one ADC adds both terms.
    uint8_t quotient;
    __asm__("mov %1,%0\n\tlsr %1\n\tlsr %1\n\tadc %0,%1"
            : "+r"(code),"=&r"(quotient) : : "cc");
    return code;
#else
    return code+((code+2)>>2);
#endif
}
#endif
#if LPX4_ENABLE_SPEECH
// Decode the signed four-bit amplitude shared by base and extra pulses.
static inline int8_t signedPulseAmplitude(uint8_t raw){
#if LPX4_AVR25_V9_RUNTIME
    // Flip the sign bit before subtracting eight to sign-extend the nibble.
    return (int8_t)((raw^8u)-8u);
#else
    return raw<8?(int8_t)raw:(int8_t)((int16_t)raw-16);
#endif
}
#endif
bool Lpx4HybridCore::readSubframe(){
#if LPX4_AVR_V9_PACKETS && LPX4_V9_ROM_HEADER_LAYOUT && !defined(LPX4_ENABLE_PCM16) && LPX4_USE_AVR_ASM
 const uint8_t packetFlags=LPX4_SPEECH_FLAGS;
#define LPX4_PACKET_FLAGS packetFlags
#else
#define LPX4_PACKET_FLAGS LPX4_SPEECH_FLAGS
#endif

#if LPX4_AVR25_V9_ROM_LAYOUT
 // There are at most 80 samples before the next packet or EOF. A gap
 // of 127 after the last impulse cannot reach zero in this packet.
 constexpr uint8_t idleGap=127;
#endif
#if LPX4_HAS_SPARSE80
 if(LPX4_PACKET_FLAGS&8){
#if LPX4_COMPACT_VERSION == 9
  const uint8_t raw=readBits(7),code=raw&63;
  pulsePos_[0]=compactPulsePosition(code);pulseAmp_[0]=(raw&64)?7:-8;
#else
  const uint8_t code=readBits(6);
  pulsePos_[0]=compactPulsePosition(code);pulseAmp_[0]=readOne()?7:-8;
#endif
#if LPX4_AVR25_V9_ROM_LAYOUT
  pulsePos_[1]=idleGap;
  pulseIndex_=0;return !error_;
#else
  pulseIndex_=0;pulseCount_=1;return !error_;
#endif
 }
#endif
#if LPX4_ENABLE_SPEECH
#if !LPX4_COMPACT_ONLY
 if(LPX4_PACKET_FLAGS){
  subType_=2;pulseIndex_=0;pulseCount_=2;
#else
 {
#if LPX4_AVR25_V9_ROM_LAYOUT
  uint8_t pulseCount=2;
  pulseIndex_=0;
#else
  pulseIndex_=0;pulseCount_=2;
#if LPX4_AVR25_V9_RUNTIME
  uint8_t& pulseCount=pulseCount_;
#endif
#endif
#endif
#if LPX4_AVR25_V9_RUNTIME
  // Keep the base pair in registers until the optional third pulse is known.
  uint8_t firstPos,secondPos;
  int8_t firstAmp,secondAmp;
  if(LPX4_PACKET_FLAGS&2){
   const uint8_t low=readBits(4),high=readBits(5);
   if(high>=25){error_=CORRUPT_STREAM;return false;}
   const uint8_t coordinates=LP_READ_U8(&pulseHigh[high]);
   firstPos=(low&3)|(coordinates&28);
   secondPos=20+((low>>2)|secondPulseHigh(coordinates));
   // The table bounds both positions, and the two signed nibbles are adjacent.
   const uint8_t amp=readBits(8);
   firstAmp=signedPulseAmplitude(amp&15);
   secondAmp=signedPulseAmplitude(amp>>4);
  }else{
   const uint8_t first=readBits(5),second=readBits(5);
   firstPos=compactPulsePosition(first&15);
   secondPos=20+compactPulsePosition(second&15);
   // Bit 4 contributes either 0 or 16 to the amplitude biased by -8.
   firstAmp=(int8_t)((first&16)-8);
   secondAmp=(int8_t)((second&16)-8);
  }
#else
#if LPX4_ENABLE_SPEECH_COMPACT
  uint16_t pair=0;
  uint8_t second=0;
#if LPX4_COMPACT_ONLY
  if(LPX4_PACKET_FLAGS&2){
#else
  if(speechCompact_ && LPX4_PACKET_FLAGS==6){
#endif
#if LPX4_COMPACT_VERSION == 9
   const uint8_t low=readBits(4),high=readBits(5);
   if(high>=25){error_=CORRUPT_STREAM;return false;}
#if LPX4_AVR_V9_PACKETS && LPX4_V9_ROM_HEADER_LAYOUT && !defined(LPX4_ENABLE_PCM16) && LPX4_USE_AVR_ASM
   uint8_t remainder=high,quotient,multiplier;
   // q=floor(high/5) in 0..4. The second product is at most 20,
   // so it also restores the ABI zero register before returning.
   __asm__("ldi %2,52\n\tmul %0,%2\n\tmov %1,r1\n\t"
       "ldi %2,5\n\tmul %1,%2\n\tsub %0,r0\n\t"
       "lsl %0\n\tlsl %0\n\tlsl %1\n\tlsl %1"
       : "+&d"(remainder),"=&r"(quotient),"=&d"(multiplier) : : "r0","r1","cc");
   pair=(low&3)|remainder;
   second=(low>>2)|quotient;
#else
   const uint8_t coordinates=LP_READ_U8(&pulseHigh[high]);
   pair=(low&3)|(coordinates&28);
   second=(low>>2)|secondPulseHigh(coordinates);
#endif
#else
   pair=readBits(8);pair|=(uint16_t)readOne()<<8;
   if(pair>=400){error_=CORRUPT_STREAM;return false;}
   // For n=0..399: floor(n/20)=floor(floor(n/4)/5).
   // x*205>>10 is exact /5 for x=0..99; product fits unsigned16.
   second=((uint16_t)(uint8_t)(pair>>2)*205u)>>10;
#endif
  }
#endif
  for(uint8_t i=0;i<2;i++){
   uint8_t pos;
   int8_t amp;
   if(!(LPX4_PACKET_FLAGS&2)){
#if LPX4_COMPACT_VERSION == 9
    const uint8_t raw=readBits(5);
    pos=compactPulsePosition(raw&15);
    amp=(raw&16)?8:-8;
#else
    pos=compactPulsePosition(readBits(4));
    amp=readOne()?8:-8;
#endif
   }else{
#if LPX4_ENABLE_SPEECH_COMPACT
#if LPX4_COMPACT_ONLY
#if LPX4_COMPACT_VERSION == 9
    pos=i?second:(uint8_t)pair;
#else
    pos=i?second:(uint8_t)(pair-second*20);
#endif
#else
    if(speechCompact_)pos=i?second:(uint8_t)(pair-second*20);
    else
#endif
#endif
#if !LPX4_COMPACT_ONLY
    pos=readBits(5);
#endif
    const uint8_t raw=readBits(4);
    amp=signedPulseAmplitude(raw);
    if(pos>=20){error_=CORRUPT_STREAM;return false;}
   }
   pulsePos_[i]=pos+i*20;pulseAmp_[i]=amp;
  }
#endif
#if LPX4_ENABLE_SPEECH_COMPACT
#if LPX4_COMPACT_ONLY
  if((LPX4_PACKET_FLAGS&128) && readOne()){
#else
  if((speechCompact_&128) && readOne()){
#endif
   const uint8_t pos=readBits(6),raw=readBits(4);
   const int8_t amp=signedPulseAmplitude(raw);
   if(pos>=40){error_=CORRUPT_STREAM;return false;}
#if LPX4_AVR25_V9_RUNTIME
   if(pos==firstPos)firstAmp+=amp;
   else if(pos==secondPos)secondAmp+=amp;
   else{
    pulseCount=3;
    if(pos<secondPos){
     pulsePos_[2]=secondPos;pulseAmp_[2]=secondAmp;
     if(pos<firstPos){secondPos=firstPos;secondAmp=firstAmp;firstPos=pos;firstAmp=amp;}
     else {secondPos=pos;secondAmp=amp;}
    }else {pulsePos_[2]=pos;pulseAmp_[2]=amp;}
   }
#elif LPX4_AVR25_V9_ROM_LAYOUT
   // Insert the extra in one forward pass. A displaced base pulse becomes
   // the next insertion, and a collision merges the amplitude in place.
   uint8_t insertPos=pos;
   int8_t insertAmp=amp;
   for(uint8_t i=0;i<2;++i){
    const uint8_t next=pulsePos_[i];
    if(insertPos==next){pulseAmp_[i]+=insertAmp;break;}
    if(insertPos<next){
     pulsePos_[i]=insertPos;insertPos=next;
     const int8_t nextAmp=pulseAmp_[i];
     pulseAmp_[i]=insertAmp;insertAmp=nextAmp;
    }
    if(i==1){pulsePos_[2]=insertPos;pulseAmp_[2]=insertAmp;pulseCount=3;}
   }
#else
   uint8_t at=0;
   while(at<2 && pulsePos_[at]<pos)++at;
   if(at<2 && pulsePos_[at]==pos)pulseAmp_[at]+=amp;
   else{
    for(uint8_t j=2;j>at;--j){pulsePos_[j]=pulsePos_[j-1];pulseAmp_[j]=pulseAmp_[j-1];}
    pulsePos_[at]=pos;pulseAmp_[at]=amp;pulseCount_=3;
   }
#endif
  }
#endif
#if LPX4_COMPACT_VERSION == 9
#if LPX4_AVR25_V9_RUNTIME || LPX4_AVR25_V9_ROM_LAYOUT
#if LPX4_AVR25_V9_RUNTIME
  // Store positions as gaps once the pulses are ordered.
  if(pulseCount==3)pulsePos_[2]-=secondPos+1;
  pulsePos_[0]=firstPos;pulsePos_[1]=secondPos-firstPos-1;
  pulseAmp_[0]=firstAmp;pulseAmp_[1]=secondAmp;
#else
  if(pulseCount==3)pulsePos_[2]-=pulsePos_[1]+1;
  pulsePos_[1]-=pulsePos_[0]+1;
#endif
#if LPX4_AVR25_V9_ROM_LAYOUT
  pulsePos_[pulseCount]=idleGap;
#endif
#else
#if LPX4_AVR_V9_PACKETS && LPX4_V9_ROM_HEADER_LAYOUT && !defined(LPX4_ENABLE_PCM16) && LPX4_USE_AVR_ASM
  if(pulseCount_==3)pulsePos_[2]-=pulsePos_[1]+1;
  pulsePos_[1]-=pulsePos_[0]+1;
#else
  for(uint8_t i=pulseCount_-1;i;--i)pulsePos_[i]-=pulsePos_[i-1]+1;
#endif
#endif
#endif
  return !error_;
 }
#endif
#if !LPX4_COMPACT_ONLY
#if LPX4_V3_FEATURES & 32
 if((formatFeatures_&32) && !mode_){
  subType_=riceK_=0;
#if LPX4_ALLOW_SPARSE
  pulseIndex_=pulseCount_=0;
#endif
  return !error_;
 }
#endif
#if LPX4_V3_FEATURES & 16
 const bool repeated=(formatFeatures_&16) && !readOne();
 if(!repeated)
#endif
 subType_=readBits(2);
#if LPX4_ALLOW_SPARSE
 pulseIndex_=pulseCount_=0;
#endif
 if(subType_==3){error_=CORRUPT_STREAM;return false;}
 if(subType_==0){
#if LPX4_V3_FEATURES & 16
   if(!repeated)
#endif
   riceK_=readBits(3);
   if(riceK_==7 && mode_!=3){error_=CORRUPT_STREAM;return false;}
 }else{
#if LPX4_V3_FEATURES & 16
   if(!repeated){
#endif
   lag_=(uint8_t)(18+readBits(7));
   gain_=readBits(5);
#if LPX4_V3_FEATURES & 16
   }
#endif
   if(lag_>145){error_=CORRUPT_STREAM;return false;}
   if(subType_==1){
#if LPX4_V3_FEATURES & 16
    if(!repeated)
#endif
    riceK_=readBits(3);
   }
   else{
#if LPX4_ALLOW_SPARSE
     pulseCount_=readBits(4);
     if(pulseCount_>LPX4_MAX_PULSES){error_=CORRUPT_STREAM;return false;}
     const uint8_t remaining=(uint8_t)(remaining_>=40?40:remaining_);
     for(uint8_t i=0;i<pulseCount_;i++){
       pulsePos_[i]=readBits(6);
       const uint8_t z=readBits(5);
       pulseAmp_[i]=(z&1)?-(int8_t)((z+1)>>1):(int8_t)(z>>1);
       if(pulsePos_[i]>=remaining || (i && pulsePos_[i]<=pulsePos_[i-1])){
         error_=CORRUPT_STREAM;return false;
       }
     }
#else
     error_=UNSUPPORTED;
     return false;
#endif
   }
 }
 return !error_;
#endif
}
#undef LPX4_PACKET_FLAGS
// Excitation reconstruction and quantized pitch history.
int16_t Lpx4HybridCore::pitchPredict() const{
#if LPX4_FAST_PITCH
#if !LPX4_COMPACT_ONLY
 if(!mode_)return 0;
#endif
 const int8_t x=LPX4_PITCH_RING_SAMPLE(ringQ_,(uint8_t)(ringCursor_-lag_));
#if LPX4_FAST_PITCH&2
 if(!x)return 0;
#endif
#if LPX4_FAST_PITCH&4
 if(!gain_)return 0;
#endif
#if LPX4_AVR5_SAMPLE_LEAF
 int8_t v=lpx4PitchQ4(x,gain_>>4,LPX4_AVR25_V9_RUNTIME);
#else
 int8_t v=lpx4PitchQ4(x,gain_,LPX4_AVR25_V9_RUNTIME);
#endif
// v5 gain is0..14 and history is-32..31: prediction is already-28..27.
#if !LPX4_COMPACT_ONLY
 const int8_t low=-(int8_t)quantLimit_,high=(int8_t)(quantLimit_-1);
 if(v<low)v=low;
 if(v>high)v=high;
#endif
 return v;
#else
 const int8_t x=LPX4_PITCH_RING_SAMPLE(ringQ_,(uint8_t)(ringCursor_-lag_));
 int16_t v=(int16_t)(((int8_t)gain_*x+8)>>4);
#if !LPX4_COMPACT_ONLY
 if(!mode_)return 0;
 const int16_t lim=quantLimit_;
 if(v < -lim)v=-lim;
 if(v >= lim)v=lim-1;
#endif
 return v;
#endif
}
#if !LPX4_COMPACT_ONLY
// Valid decodeCode callers have error==NONE. Nonzero cache contains a
// terminator within bitsLeft (all unused cache bits are zero by construction).
// Empty/all-zero caches retain the exact bounded refill/error path.
#ifndef LPX4_FAST_UNARY
#define LPX4_FAST_UNARY 1
#endif
#if LPX4_FAST_UNARY < 0 || LPX4_FAST_UNARY > 2
#error LPX4_FAST_UNARY must be 0,1 or2
#endif
#if LPX4_FAST_UNARY==2
static const uint8_t LP_PROGMEM unaryNibble[16]={4,0,1,0,2,0,1,0,3,0,1,0,2,0,1,0};
#endif
bool Lpx4HybridCore::readUnary8(uint8_t& high){
 high=0;
#if LPX4_FAST_UNARY
 if(bitBuffer_){
   uint8_t cache=bitBuffer_;
#if LPX4_FAST_UNARY==2
   if(!(cache&15)){cache>>=4;high=4;}
   high+=LP_READ_U8(&unaryNibble[cache&15]);
   cache=bitBuffer_>>high;
#else
   while(!(cache&1)){cache>>=1;++high;}
#endif
   bitBuffer_=cache>>1;bitsLeft_-=high+1;
#ifdef LPX3_COST_INSTRUMENT
   bitCalls_+=high+1;
#endif
   return true;
 }
#endif
 while(!readOne()){
   if(error_||++high>8){error_=CORRUPT_STREAM;return false;}
 }
 return true;
}
#endif
#if LPX4_AVR5_SAMPLE_LEAF
// GNU AVR ABI: state arrives in r25:r24. Signed Q4 returns in r25:r22.
// The state pointer begins at blockStep_. Every byte offset is constant,
// and the ring page byte is fixed independently of the arithmetic backend.
__attribute__((noinline,noclone)) int32_t Lpx4HybridCore::decodeCompactAvr5(uint8_t* state){
    register uint8_t* input __asm__("r24")=state;
    register int32_t result __asm__("r22");
    __asm__ volatile(
        "movw r30,%A[state]\n\t"
        "ldd r18,Z+%[gain]\n\tldd r19,Z+%[lag]\n\tldd r20,Z+%[cursor]\n\t"
        "mov r26,r20\n\tsub r26,r19\n\tldi r27,hi8(%[ring])\n\tld r21,X\n\t"
        // The block parser stored the even gain multiplied by sixteen.
        // Multiplying by this value moves the Q4
        // quotient into the product high byte. The low-byte carry rounds it.
        "mulsu r21,r18\n\tlsl r0\n\tmov r18,r1\n\t"
        "clr __zero_reg__\n\tadc r18,__zero_reg__\n\t"
        "ldd r22,Z+%[index]\n\tldd r23,Z+%[count]\n\tcp r22,r23\n\tbrsh 4f\n\t"
        "movw r26,r30\n\tadd r26,r22\n\tadc r27,__zero_reg__\n\t"
        "subi r26,lo8(-%[pos])\n\tsbci r27,hi8(-%[pos])\n\t"
        "ld r23,X\n\tdec r23\n\tst X,r23\n\tbrpl 2f\n\t"
        "adiw r26,%[amp]\n\tld r23,X\n\tinc r22\n\tstd Z+%[index],r22\n\t"
        // Only a pulse can push the excitation outside the six-bit range.
        "add r18,r23\n\tsubi r18,224\n\tcpi r18,64\n\tbrlo 1f\n\t"
        "cpi r18,128\n\tsbc r18,r18\n\tandi r18,63\n\t"
        "1: subi r18,32\n\t"
        "2: ldi r27,hi8(%[ring])\n\t4: mov r26,r20\n\tst X,r18\n\t"
        "inc r20\n\tstd Z+%[cursor],r20\n\tld r20,Z\n\tldd r21,Z+1\n\t"
        "mulsu r18,r20\n\tmovw r22,r0\n\tsbc r24,r24\n\t"
        "mulsu r18,r21\n\tsbc r25,r25\n\tor r25,r24\n\t"
        "add r23,r0\n\tadc r24,r1\n\tclr __zero_reg__"
        : "=r"(result) : [state]"r"(input),[gain]"I"(offsetof(Lpx4HybridCore,gain_)-offsetof(Lpx4HybridCore,blockStep_)),[lag]"I"(offsetof(Lpx4HybridCore,lag_)-offsetof(Lpx4HybridCore,blockStep_)),
            [cursor]"I"(offsetof(Lpx4HybridCore,ringCursor_)-offsetof(Lpx4HybridCore,blockStep_)),[index]"I"(offsetof(Lpx4HybridCore,pulseIndex_)-offsetof(Lpx4HybridCore,blockStep_)),
            [count]"I"(offsetof(Lpx4HybridCore,pulseCount_)-offsetof(Lpx4HybridCore,blockStep_)),[pos]"n"(offsetof(Lpx4HybridCore,pulsePos_)-offsetof(Lpx4HybridCore,blockStep_)),
            [amp]"I"(offsetof(Lpx4HybridCore,pulseAmp_)-offsetof(Lpx4HybridCore,pulsePos_)),
            [ring]"i"(ringQ_) : "r0","r1","r18","r19","r20","r21","r26","r27","r30","r31","cc","memory");
    return result;
}
#endif

bool Lpx4HybridCore::decodeCode(int8_t& q){
#if LPX4_COMPACT_ONLY
#if LPX4_AVR25_V9_RUNTIME || LPX4_AVR25_V9_ROM_LAYOUT
 // The caller has already checked parser errors. Pitch alone is -28..27,
 // so only a sample with an innovation can need saturation to -32..31.
 int8_t decoded=(int8_t)pitchPredict();
#if LPX4_AVR25_V9_ROM_LAYOUT
#if LPX4_AVR25_V9_RUNTIME
 // All initial gaps and the idle tail fit in a nonnegative int8_t.
 // DEC sets N precisely when the previous gap was zero. ST preserves N.
 uint8_t* gap=&pulsePos_[pulseIndex_];
 __asm__ goto("ld __tmp_reg__,%a0\n\tdec __tmp_reg__\n\tst %a0,__tmp_reg__\n\tbrpl %l[noPulse]"
              : : "e"(gap) : "r0","cc","memory" : noPulse);
 {
#else
 if(--pulsePos_[pulseIndex_]==255){
#endif
  decoded+=pulseAmp_[pulseIndex_++];
  if(decoded < -32)decoded=-32;
  if(decoded > 31)decoded=31;
 }
#if LPX4_AVR25_V9_RUNTIME
noPulse:
#endif
#else
 if(pulseIndex_<pulseCount_){
  if(pulsePos_[pulseIndex_]){
   --pulsePos_[pulseIndex_];
  }else{
   decoded+=pulseAmp_[pulseIndex_++];
   if(decoded < -32)decoded=-32;
   if(decoded > 31)decoded=31;
  }
 }
#endif
 q=decoded;
 LPX4_PITCH_RING_SAMPLE(ringQ_,ringCursor_++)=decoded;
 return true;
#else
#if LPX4_COMPACT_VERSION == 9
 // Pitch is -28..27; one merged innovation is -16..16. The unclipped
 // sum fits signed8 for every P4/P6/sparse80 packet, including extras.
 int8_t decoded=(int8_t)pitchPredict();
#else
 int16_t decoded=pitchPredict();
#endif
#if LPX4_COMPACT_VERSION == 9
 if(pulseIndex_<pulseCount_ && !pulsePos_[pulseIndex_]){
#elif LPX4_HAS_SPARSE80
 const uint8_t phase=(LPX4_SPEECH_FLAGS&8)?(subIndex_&3):(subIndex_&1);
 const uint8_t position=(uint8_t)(subPos_+(uint8_t)(phase*20));
 if(pulseIndex_<pulseCount_ && pulsePos_[pulseIndex_]==position){
#else
 if(pulseIndex_<pulseCount_ && pulsePos_[pulseIndex_]==(subPos_+((subIndex_&1)?20:0))){
#endif
  decoded+=pulseAmp_[pulseIndex_++];
 }
#if LPX4_COMPACT_VERSION == 9
 else if(pulseIndex_<pulseCount_)--pulsePos_[pulseIndex_];
#endif
 if(error_)return false;
 if(decoded < -32)decoded=-32;
 if(decoded > 31)decoded=31;
 q=(int8_t)decoded;LPX4_PITCH_RING_SAMPLE(ringQ_,ringCursor_++)=q;
 return true;
#endif
#else
 int16_t decoded=0;
 if(subType_==0){
   if(!mode_)decoded=0;
   else if(riceK_==7){
     decoded=readHuffman3();
   }else if(riceK_){
     uint8_t high;
     if(!readUnary8(high))return false;
     const uint16_t z=(uint16_t)((high<<riceK_)|readBits(riceK_));
     decoded=(z&1)?-(int16_t)((z+1)>>1):(int16_t)(z>>1);
   }else decoded=(int16_t)readBits(mode_)-(int16_t)quantLimit_;
 }else{
   decoded=pitchPredict();
   int16_t d=0;
   if(subType_==1){
     if(riceK_==7)d=(int8_t)readBits(8);
     else{
       uint8_t high;
       if(!readUnary8(high))return false;
       const uint16_t z=(uint16_t)((high<<riceK_) | (riceK_?readBits(riceK_):0));
       d=(z&1)?-(int16_t)((z+1)>>1):(int16_t)(z>>1);
     }
   }
#if LPX4_ALLOW_SPARSE
   else if(pulseIndex_<pulseCount_ && pulsePos_[pulseIndex_]==(subPos_+((subIndex_&1)?20:0))){
       d=pulseAmp_[pulseIndex_++];
   }
#endif
   decoded+=d;
   if(subType_==2){
     if(!mode_)decoded=0;
     else{
       const int16_t lim=quantLimit_;
       if(decoded < -lim)decoded=-lim;
       if(decoded >= lim)decoded=lim-1;
     }
   }
 }
 if(error_)return false;
 if(mode_){
   const int16_t lim=quantLimit_;
   if(decoded < -lim || decoded >= lim){error_=CORRUPT_STREAM;return false;}
 }else if(decoded){error_=CORRUPT_STREAM;return false;}
 q=(int8_t)decoded;
 LPX4_PITCH_RING_SAMPLE(ringQ_,ringCursor_++)=q;
 return true;
#endif
}
#if !LPX4_FLOAT_SYNTHESIS
// Guard the 32x16 product on pathological/invalid LPX3 LSF vectors.
// Normal spectra take the single-multiply fast path; split product only if
// absolute polynomial coefficient would overflow signed int32 when *8192.
static inline int32_t polyMulQ12(int32_t v,int16_t c){
    if(v<=250000L && v>=-250000L)return lpx4Shift12(lpx4Mul32x16(v,c));
    const int32_t hi=truncShift(v,4);
    int8_t rem=(uint8_t)v&15;
    if(v<0 && rem)rem-=16;
    // Preserve the original separate floors of the two split products.
    return (lpx4Mul32x16(hi,c)>>8)+lpx4Shift12(lpx4Mul8x16(rem,c));
}
#if LPX4_USE_AVR5_POLYNOMIAL_MUL && LPX4_COMPACT_VERSION!=9
// The direct branch bounds x to signed24 and the product to signed32.
// Treat the low two bytes of x as unsigned and the third as signed.
// Six byte products suffice modulo 2^32. Restore r1 before returning to C++.
static __attribute__((noinline)) int32_t polyDirectProduct(int32_t x,int16_t y){
    uint32_t result;
    uint8_t zero;
    __asm__(
        "clr %1\n\t"
        "mul %A2,%A3\n\tmovw %A0,r0\n\t"
        "mulsu %B3,%B2\n\tmovw %C0,r0\n\t"
        "mul %A3,%B2\n\tadd %B0,r0\n\tadc %C0,r1\n\tadc %D0,%1\n\t"
        "mulsu %B3,%A2\n\tsbc %D0,%1\n\tadd %B0,r0\n\tadc %C0,r1\n\tadc %D0,%1\n\t"
        "mulsu %C2,%A3\n\tadd %C0,r0\n\tadc %D0,r1\n\t"
        "mul %C2,%B3\n\tadd %D0,r0\n\t"
        "clr __zero_reg__\n\t"
        : "=&r"(result),"=&r"(zero) : "a"(x),"a"(y) : "r0","r1","cc");
    return (int32_t)result;
}
#endif
// Conversion-only bound: before the fifth quadratic, each coefficient is
// bounded by 4096*binomial(9,k), at most 516096. Earlier factors use the
// direct path, so no split-floor error enters that bound. Consequently
// trunc(v/16) fits signed16 (|hi|<=32256). Keep the exact 250000 threshold
// and both separate floors; the unrestricted polynomial helper stays above.
#if LPX4_POLY24_WORKSPACE
typedef int PolyCoefficient __attribute__((mode(PSI)));

// Within the polynomial workspace bound, floor(v / 16) fits signed16.
template<class Coefficient>
static inline __attribute__((always_inline)) int16_t polyHighWord(Coefficient v){
    int16_t hi;
    uint8_t temp;
    __asm__(
        "mov %A0,%A2\n\tswap %A0\n\tandi %A0,15\n\t"
        // XOR the swapped middle byte, mask it, and cancel its low nibble.
        "mov %B0,%B2\n\tswap %B0\n\teor %A0,%B0\n\t"
        "andi %B0,15\n\teor %A0,%B0\n\t"
        "mov %1,%C2\n\tswap %1\n\tandi %1,240\n\tor %B0,%1"
        : "=&d"(hi),"=&d"(temp) : "r"(v) : "cc");
    return hi;
}
#endif

#if LPX4_AVR25_V9_RUNTIME
// Both bytes of hi use the same seven shift/add rounds. The residue
// uses the final four rounds. The intermediate sum fits for |c|<=8192.
static inline __attribute__((always_inline)) PolyCoefficient polyGroupedQ12(int8_t residue,int16_t hi,int16_t c,int8_t directMask){
    PolyCoefficient out;
    uint8_t phase;
    __asm__(
        "mov %A0,%2\n\tclr %B0\n\tclr %C0\n\t"
        "lsr %A0\n\tclr %1\n\trjmp 4f\n\t2:\n\t.rept 3\n\t"
        "brcc 1f\n\tadd %B0,%A4\n\tadc %C0,%B4\n\t"
        "1: asr %C0\n\tror %B0\n\tror %A0\n\t.endr\n\t4:\n\t.rept 4\n\t"
        "brcc 1f\n\tadd %B0,%A4\n\tadc %C0,%B4\n\t"
        "1: asr %C0\n\tror %B0\n\tror %A0\n\t.endr\n\t"
        "dec %1\n\tbrmi 6f\n\tbreq 8f\n\t"
        "brcc 1f\n\tadd %B0,%A4\n\tadc %C0,%B4\n\t"
        "1: asr %C0\n\tror %B0\n\t"
        "mov %A0,%B3\n\tlsr %A0\n\trjmp 2b\n\t"
        // Negative signed low nibble equals its four unsigned bits minus 16.
        "6: sbrs %2,7\n\trjmp 7f\n\tsub %B0,%A4\n\tsbc %C0,%B4\n\t"
        // Split rounding discards the residue's low byte before adding it
        // to the word product. Direct rounding keeps that byte for carry.
        "7: sbrs %5,7\n\tclr %B0\n\t"
        "ldi %1,2\n\tmov %A0,%A3\n\tlsr %A0\n\trjmp 2b\n\t"
        // The final bit is the signed weight of the high word byte.
        "8: brcc 1f\n\tsub %B0,%A4\n\tsbc %C0,%B4\n\t"
        "1: asr %C0\n\tror %B0\n\tror %A0"
        : "=&r"(out),"=&d"(phase)
        : "r"(residue),"r"(hi),"r"(c),"r"(directMask) : "cc");
    return out;
}

static inline PolyCoefficient polyCosineMulQ12(PolyCoefficient v,int16_t c){
    int16_t hi=polyHighWord(v);
    // A whole-product floor is needed for -250000 <= v < 250000.
    // At +250000 the residue is zero, so both rounding rules agree.
    uint16_t biased=(uint16_t)hi+15625u;
    int8_t directMask;
    __asm__("subi %A1,lo8(31250)\n\tsbci %B1,hi8(31250)\n\tsbc %0,%0"
            : "=&r"(directMask),"+&d"(biased) : : "cc");
    int8_t residue=(uint8_t)v&15;
    if(!directMask && hi<0 && residue){++hi;residue-=16;}
    return polyGroupedQ12(residue,hi,c,directMask);
}
#elif LPX4_POLY24_WORKSPACE
static inline PolyCoefficient polyCosineMulQ12(PolyCoefficient v,int16_t c){
    int16_t hi=polyHighWord(v);
    const bool direct=(uint16_t)(hi+15625U)<31250U;
    int8_t residue=(uint8_t)v&15;
    // Restore truncating division for the independently rounded split path.
    if(!direct && hi<0 && residue){++hi;residue-=16;}
    // Multiply the signed low nibble by c, then keep bits 4..19.
    int16_t nibble;
    uint8_t high;
    __asm__(
        "mulsu %2,%A3\n\tmovw %A0,r0\n\tsbc %1,%1\n\t"
        "muls %2,%B3\n\tadd %B0,r0\n\tadc %1,r1\n\t"
        "swap %A0\n\tandi %A0,15\n\tswap %B0\n\t"
        "eor %A0,%B0\n\tandi %B0,15\n\teor %A0,%B0\n\t"
        "swap %1\n\tandi %1,240\n\tor %B0,%1\n\tclr __zero_reg__"
        : "=&d"(nibble),"=&d"(high) : "a"(residue),"a"(c) : "r0","r1","cc");
    const int32_t word=lpx4Mul16(hi,c);
    // At +250000 residue is zero, so either rounding rule is exact there.
    return direct?(word+nibble)>>8:(word>>8)+(nibble>>8);
}
#else
static inline int32_t polyCosineMulQ12(int32_t v,int16_t c){
#if LPX4_USE_AVR5_POLYNOMIAL_MUL
    if(v<=250000L && v>=-250000L)return lpx4Shift12(polyDirectProduct(v,c));
    int16_t hi=(int16_t)(v>>4);
    int8_t rem=(uint8_t)v&15;
    // Turn the floor and nonnegative remainder into the truncating split.
    if(v<0 && rem){++hi;rem-=16;}
    return (lpx4Mul16(hi,c)>>8)+lpx4Shift12(lpx4Mul8x16(rem,c));
#elif LPX4_USE_AVR_NOMUL_ASM
    if(v<=250000L && v>=-250000L)return lpx4Shift12(lpx4Mul32x16(v,c));
    const int16_t hi=(int16_t)truncShift(v,4);
    int8_t rem=(uint8_t)v&15;
    if(v<0 && rem)rem-=16;
    return (lpx4Mul16(hi,c)>>8)+lpx4Shift12(lpx4Mul8x16(rem,c));
#else
    // The same fixed-point C reference remains explicitly selectable on AVR.
    return polyMulQ12(v,c);
#endif
}
#endif
#if LPX4_MEMORY_PROFILE == LPX4_MEMORY_PROFILE_SRAM512
// The next 111 ring slots are dead: the largest v5 pitch lag is 145, and
// every future code is stored before it can be read. Align within those slots
// so each memcpy stays inside the physical ring even when the workspace wraps.
// memcpy retains byte-storage object lifetimes, alignment and aliasing rules.
static inline int32_t ringPolyGetAt(const int8_t* ring,uint8_t offset){
    int32_t value;
    memcpy(&value,LPX4_PITCH_RING_ADDRESS(ring,offset),sizeof(value));
    return value;
}
static inline void ringPolyPutAt(int8_t* ring,uint8_t offset,int32_t value){
    memcpy(LPX4_PITCH_RING_ADDRESS(ring,offset),&value,sizeof(value));
}
static inline int32_t ringPolyGet(const int8_t* ring,uint8_t base,uint8_t index){
    return ringPolyGetAt(ring,base+index*4);
}
static inline void ringPolyPut(int8_t* ring,uint8_t base,uint8_t index,int32_t value){
    ringPolyPutAt(ring,base+index*4,value);
}
// Universal v5/v9 builds reinvest part of the software-product size saving
// in the exact half-P recurrence. Keep the compact fixed-header ROM recipe
// unchanged: its images have a separate, smaller application Flash budget.
#if defined(LPX4_FIXED_SPEECH_FLAGS)
static const bool halfPolynomialP=false;
#else
static const bool halfPolynomialP=true;
#endif
#if LPX4_POLY24_WORKSPACE
// Degree-11 coefficients fit signed24: 4096*binomial(11,5)+1 is
// below 2^21, and twice that bound also fits signed24. Keep the
// four-byte slot stride so a word never straddles the ring boundary.
static inline PolyCoefficient ringPolyLoad24(const int8_t* ring,uint8_t offset){
    PolyCoefficient value;
    memcpy(&value,LPX4_PITCH_RING_ADDRESS(ring,offset),sizeof(value));
    return value;
}
static inline void ringPolyStore24(int8_t* ring,uint8_t offset,PolyCoefficient value){
    memcpy(LPX4_PITCH_RING_ADDRESS(ring,offset),&value,sizeof(value));
}
static inline __attribute__((always_inline)) void ringPolyFactor(int8_t* ring,uint8_t base,int16_t c,uint8_t n,bool symmetric){
    uint8_t offset;
    PolyCoefficient previous,current;
    if(symmetric){
        // P's new middle starts with a copy of the old middle.
        offset=base+2*n;
        previous=current=ringPolyLoad24(ring,offset-4);
    }else{
        // Q's trailing unit is always -4096. Supply it in the loop's
        // first iteration and omit its store in the new polynomial.
        offset=base+4*(n-1);
        previous=ringPolyLoad24(ring,offset-4);
        ringPolyStore24(ring,offset+4,previous-c);
        current=-4096;
    }
#if LPX4_USE_AVR_ASM && LPX4_PLAYER_PITCH_PAGE
    // Change only ZL so a wrapped coefficient stays in the same page.
    int8_t* cursor=pitchRingAddress(ring,offset);
    const uint8_t stop=base+4;
    register int16_t factor __asm__("r20")=c;
    __asm__ volatile(
        "cp r30,%4\n\tbrne 1f\n\trjmp 6f\n\t"
        // Form floor(previous/16) in r17:r16 and test its direct range.
        "1: mov r16,%A0\n\tswap r16\n\tandi r16,15\n\t"
        "mov r17,%B0\n\tswap r17\n\teor r16,r17\n\tandi r17,15\n\teor r16,r17\n\t"
        "mov r18,%C0\n\tswap r18\n\tandi r18,240\n\tor r17,r18\n\t"
        "movw r22,r16\n\tsubi r22,lo8(-15625)\n\tsbci r23,hi8(-15625)\n\t"
        "subi r22,lo8(31250)\n\tsbci r23,hi8(31250)\n\tsbc r19,r19\n\t"
        // Floor((previous & 15) * factor / 16) in r25:r24.
        "mov r18,%A0\n\tswap r18\n\tandi r18,240\n\t"
        "mul r18,r20\n\tmov r24,r1\n\t"
        "mulsu r21,r18\n\tadd r24,r0\n\tmov r25,r1\n\tclr r23\n\tadc r25,r23\n\t"
        // The split path truncates the original coefficient and discards
        // the seed's low byte, making its floor independent of the product.
        "tst r19\n\tbrne 3f\n\tsbrs r17,7\n\trjmp 2f\n\ttst r18\n\tbreq 2f\n\t"
        "subi r16,255\n\tsbci r17,255\n\tsub r24,r20\n\tsbc r25,r21\n\t"
        "2: clr r24\n\t3: subi r25,128\n\t"
        // Add the biased 16-bit seed before discarding the low-low byte.
        "muls r17,r21\n\tmovw r18,r0\n\t"
        "mul r16,r20\n\tadd r0,r24\n\tadc r1,r25\n\tmov r22,r1\n\tadc r18,r23\n\tadc r19,r23\n\t"
        "mulsu r17,r20\n\tsbc r19,r23\n\tadd r22,r0\n\tadc r18,r1\n\tadc r19,r23\n\t"
        "mulsu r21,r16\n\tsbc r19,r23\n\tadd r22,r0\n\tadc r18,r1\n\tadc r19,r23\n\t"
        "subi r22,128\n\tsbc r18,r23\n\tsbc r19,r23\n\t"
        // The cursor is page-relative. Move only ZL to keep modulo-256 addressing.
        "add r22,%A1\n\tadc r18,%B1\n\tadc r19,%C1\n\t"
        "mov %A1,%A0\n\tmov %B1,%B0\n\tmov %C1,%C0\n\t"
        "subi r30,8\n\tld %A0,Z\n\tldd %B0,Z+1\n\tldd %C0,Z+2\n\t"
        "add r22,%A0\n\tadc r18,%B0\n\tadc r19,%C0\n\t"
        "subi r30,248\n\tst Z,r22\n\tstd Z+1,r18\n\tstd Z+2,r19\n\t"
        "subi r30,4\n\tcp r30,%4\n\tbreq 6f\n\trjmp 1b\n\t"
        "6: mov r17,r21\n\tlsl r17\n\tsbc r17,r17\n\t"
        "add %A1,r20\n\tadc %B1,r21\n\tadc %C1,r17\n\t"
        "st Z,%A1\n\tstd Z+1,%B1\n\tstd Z+2,%C1\n\tclr __zero_reg__"
        : "+&r"(previous),"+&r"(current),"+&z"(cursor) : "r"(factor),"r"(stop)
        : "r0","r1","r16","r17","r18","r19","r24","r25","r22","r23","cc","memory");
#else
    // Both polynomials use the same descending recurrence and Q12 floors.
    // The first factor already has its two edge values. Its recurrence
    // is empty, and the normal final store writes the first coefficient.
    while(offset!=(uint8_t)(base+4)){
        const PolyCoefficient product=polyCosineMulQ12(previous,c);
        const PolyCoefficient earlier=ringPolyLoad24(ring,offset-8);
        ringPolyStore24(ring,offset,earlier+product+current);
        // The previous operand becomes the current coefficient after stepping back.
        current=previous;
        previous=earlier;
        offset-=4;
    }
    ringPolyStore24(ring,offset,c+current);
#endif
}
#elif LPX4_USE_AVR5_POLYNOMIAL_MUL || (LPX4_USE_AVR_NOMUL_ASM && !defined(LPX4_FIXED_SPEECH_FLAGS))
static inline __attribute__((always_inline)) void ringPolyFactor(int8_t* ring,uint8_t base,int16_t c,uint8_t n,bool symmetric){
    uint8_t j;
    int32_t previous;
    if(symmetric){
        // P retains only its lower half. Seed the new middle from P[j-1].
        j=n>>1;
        previous=ringPolyGet(ring,base,j-1);
        ringPolyPut(ring,base,j,previous);
    }else{
        // Q retains both halves and its exact signed trailing unit.
        const int32_t trailing=ringPolyGet(ring,base,n-1);
        ringPolyPut(ring,base,n+1,trailing);
        previous=ringPolyGet(ring,base,n-2);
        ringPolyPut(ring,base,n,previous+(trailing<0?-(int32_t)c:(int32_t)c));
        j=n-1;
    }
    // n>=4 here. Before each update, previous holds the old p[j-1].
    // The old p[j-2] becomes the multiply operand for the next word.
    uint8_t at=base+j*4;
    do{
        const int32_t product=polyCosineMulQ12(previous,c);
        const int32_t earlier=ringPolyGetAt(ring,at-8);
        const int32_t value=earlier+product+ringPolyGetAt(ring,at);
        ringPolyPutAt(ring,at,value);
        previous=earlier;
        at-=4;
    }while(at!=(uint8_t)(base+4));
    ringPolyPut(ring,base,1,c+ringPolyGet(ring,base,1));
}
#else
static inline __attribute__((always_inline)) void ringPolyFactor(int8_t* ring,uint8_t base,int16_t c,uint8_t n,bool symmetric){
    // Same descending recurrence and separately rounded products as polyFactor.
    uint8_t j;
    if(symmetric){
        // P starts with (1+z) and remains exactly palindromic: equal inputs
        // receive identical rounded products. Retain only its lower half.
        // The first new middle term aliases the previous middle coefficient.
        j=n>>1;ringPolyPut(ring,base,j,ringPolyGet(ring,base,j-1));
    }else{
        // Q's antisymmetry does not survive separate floor rounding.
        const int32_t trailing=ringPolyGet(ring,base,n-1);
        ringPolyPut(ring,base,n+1,trailing);
        ringPolyPut(ring,base,n,ringPolyGet(ring,base,n-2)+(trailing<0?-(int32_t)c:(int32_t)c));
        j=n-1;
    }
    for(;j>=2;--j){
        const int32_t value=ringPolyGet(ring,base,j-2)+polyCosineMulQ12(ringPolyGet(ring,base,j-1),c)+ringPolyGet(ring,base,j);
        ringPolyPut(ring,base,j,value);
    }
    ringPolyPut(ring,base,1,c+ringPolyGet(ring,base,1));
}
#endif
static_assert(sizeof(int32_t)==4,"The sram512 workspace uses four-byte words");
#else
// LSF->LPC polynomial. Independent Q12 multiplication (no floats/trig in AVR).
void Lpx4HybridCore::polyFactor(int32_t* p,int16_t c,uint8_t n){
    // Multiply by 1+c*z^-1+z^-2 IN PLACE, descending to preserve original
    // p[j-1] and p[j-2]. Eliminates 12*4=48 bytes of SRAM and two passes.
    // Retain the same ascending-contribution order as the old polyTmp method.
    p[n+1]=p[n-1];
    // The trailing unit is +/-4096, so this product has no rounding.
    p[n]=p[n-2]+(p[n-1]<0?-(int32_t)c:(int32_t)c);
    for(uint8_t j=(uint8_t)(n-1);j>=2;--j){
        p[j]=p[j-2]+polyMulQ12(p[j-1],c)+p[j];
    }
    // p[0] is initialized to 4096 and never changed by any factor.
    p[1]=c+p[1];
}
#endif
#endif // fixed polynomial helpers
// LPC spectrum conversion and anchor interpolation.
#ifndef LPX3_LPC_SEGMENTS
#define LPX3_LPC_SEGMENTS 2
#endif
#if LPX3_LPC_SEGMENTS!=1 && LPX3_LPC_SEGMENTS!=2 && LPX3_LPC_SEGMENTS!=4
#error LPX3_LPC_SEGMENTS must be 1,2,4
#endif
#define LPX4_SELECT_LSF_ENDPOINTS \
    (LPX4_COMPACT_ONLY && LPX3_LPC_SEGMENTS!=4 && \
     (LPX4_USE_AVR_NOMUL_ASM || (LPX4_USE_AVR_ASM && LPX4_COMPACT_VERSION==9)))
// LSF->LPC only on predicted polynomial anchors, not every subframe.
// Fixed anchors retain the reference integer polynomial at t=0..16.
// Floating anchors share those locations with unrounded double polynomials.
// Both modes retain the 10-pole filter and discrete excitation codes.
#if LPX4_COMPACT_ONLY && LPX3_LPC_SEGMENTS == 4
// q+1 keeps zero as the untouched-state sentinel. Four segments also use
// quarter anchors, which need the full centered-value normalization.
static inline __attribute__((always_inline)) int16_t centeredLsf(uint8_t q,uint8_t profile){
 return q ? (int16_t)((uint16_t)(q*2-1)<<((profile&2)?3:4)) : 0;
}
#endif
#if LPX4_POLY24_WORKSPACE && !(LPX4_AVR25_LSF_ASM)
// AVR-GCC 7.3.0 emits a smaller recurrence with the address operations
// left inside their branches. Keep this choice local to the converter.
__attribute__((optimize("no-code-hoisting")))
#endif
#if LPX4_AVR25_LSF_ASM
__asm__(
#include "Lpx4ConvertAvr25.inc"
);
__attribute__((always_inline))
#endif
void Lpx4HybridCore::convertLsfAt(uint8_t t,Lpx4SynthesisValue* out){
#if LPX4_AVR25_LSF_ASM
    // Keep input memory ownership and arithmetic selection independent.
    // R9/R12/R13/R16/R17 are dead at the caller and need no nested save.
    static_assert(offsetof(Lpx4HybridCore,speechProfile_)<64 && offsetof(Lpx4HybridCore,ringCursor_)<64,
                  "Converter fields must fit AVR displacement addressing");
    register Lpx4HybridCore* self __asm__("r26")=this;
    register uint8_t target __asm__("r24")=t;
    register Lpx4SynthesisValue* destination __asm__("r22")=out;
    __asm__ volatile(
        ".set lpx4_conv_ring_offset,%[ring]\n\t"
        ".set lpx4_conv_profile_offset,%[profile]\n\t"
        ".set lpx4_conv_cur_offset,%[cur]\n\t"
        ".set lpx4_conv_old_offset,%[old]\n\t"
        "rcall lpx4_tiny_convert"
        : "+x"(self),"+r"(target),"+r"(destination)
        : [ring]"n"(offsetof(Lpx4HybridCore,ringCursor_)),
          [profile]"n"(offsetof(Lpx4HybridCore,speechProfile_)),
          [cur]"n"(offsetof(Lpx4HybridCore,cur_)),
          [old]"n"(offsetof(Lpx4HybridCore,lpcAnchors_)+10*sizeof(Lpx4SynthesisValue))
        : "r0","r9","r12","r13","r16","r17","r18","r19","r20","r21","r25","r30","r31","cc","memory");
    return;
#else

#ifdef LPX3_COST_INSTRUMENT
    ++lsfConverts_;
#endif
#if LPX4_FLOAT_SYNTHESIS
    double p[12]={1.0,1.0},q[12]={1.0,-1.0};
    uint8_t pDegree=1,qDegree=1;
    for(uint8_t i=0;i<10;++i){
#if LPX4_COMPACT_ONLY
        const double bins=(LPX4_SPEECH_FLAGS&2)?64.0:32.0;
        const double previous=(static_cast<double>(prev_[i])-0.5)/bins;
        const double current=(static_cast<double>(cur_[i])-0.5)/bins;
#else
        const double previous=static_cast<double>(prev_[i])/1024.0;
        const double current=static_cast<double>(cur_[i])/1024.0;
#endif
        const double lsf=previous+(current-previous)*(static_cast<double>(t)/16.0);
        const double factor=-2.0*std::cos(lpx4FloatPi*lsf);
        if(i&1)lpx4FloatFactor(q,qDegree,factor);
        else lpx4FloatFactor(p,pDegree,factor);
    }
    for(uint8_t i=0;i<10;++i)
        out[i]=lpx4FloatClamp((p[i+1]+q[i+1])*0.5,-32767.0/4096.0,32767.0/4096.0);
#else
#if LPX4_LPC2_LSF_OVERLAY
#if LPX4_AVR_V9_PACKETS
    const uint8_t* const oldBins=reinterpret_cast<const uint8_t*>(lpcAnchors_+10);
#else
    // The portable fallback's first static conversion uses t=0.
    const uint8_t* const oldBins=staticSpectrum_?cur_:reinterpret_cast<const uint8_t*>(lpcAnchors_+10);
#endif
#define LPX4_PREVIOUS_BINS oldBins
#else
#define LPX4_PREVIOUS_BINS prev_
#endif
#if LPX4_MEMORY_PROFILE == LPX4_MEMORY_PROFILE_SRAM512
    // Lead-in <=3 plus the workspace fits in the 111 dead future slots.
    const uint8_t pbase=(uint8_t)((ringCursor_+3)&252);
#if LPX4_POLY24_WORKSPACE
    // P stores coefficients 0..5. Q stores 0..10 with the trailing unit implicit.
    const uint8_t qbase=(uint8_t)(pbase+24);
    ringPolyStore24(ringQ_,pbase,4096);
    ringPolyStore24(ringQ_,qbase,4096);
#else
    const uint8_t qbase=(uint8_t)(pbase+48);
    ringPolyPut(ringQ_,pbase,0,4096);ringPolyPut(ringQ_,qbase,0,4096);
#endif
#else
    polyP_[0]=polyQ_[0]=4096;
#endif
#if LPX4_SELECT_LSF_ENDPOINTS && !defined(LPX4_FIXED_SPEECH_FLAGS)
    // LPC segments 1/2 use t=0, 8, 16. Select the endpoints once so
    // both endpoints and the midpoint use the same centered-grid sum.
#if LPX4_COMPACT_VERSION==9
    const uint8_t* left=LPX4_PREVIOUS_BINS;
    const uint8_t* right=cur_;
    // Bit 4 selects the current endpoint. Zero selects the previous one.
    // The midpoint uses both pointers, so neither needs changing.
    __asm__("sbrc %2,4\n\tmovw %A0,%A1\n\t"
            "tst %2\n\tbrne 1f\n\tmovw %A1,%A0\n\t1:"
            : "+&w"(left),"+&w"(right) : "r"(t) : "cc");
#else
    const uint8_t* left=t==16?cur_:LPX4_PREVIOUS_BINS;
    const uint8_t* right=t==0?LPX4_PREVIOUS_BINS:cur_;
#endif
#endif
    for(uint8_t i=0;i<10;i++){
#if LPX4_SELECT_LSF_ENDPOINTS && !defined(LPX4_FIXED_SPEECH_FLAGS)
        uint8_t node=left[i]+right[i]-1;
        if(!(LPX4_SPEECH_FLAGS&2))node+=node;
#if LPX4_POLY24_WORKSPACE && LPX4_COMPACT_VERSION==9
        const int16_t cc=lpcCosineFactor(node);
#else
        const int16_t cc=(int16_t)-cosineEvenNode(node);
#endif
#elif LPX4_COMPACT_ONLY && LPX3_LPC_SEGMENTS != 4
        // For segments1/2, u is 0/1/2. Factoring centered q+1 values
        // gives the even-grid index directly, without widening and shifting back.
        const uint8_t u=t>>3;
        const uint8_t node=(uint8_t)(LPX4_PREVIOUS_BINS[i]*(2-u)+cur_[i]*u-1)<<((LPX4_SPEECH_FLAGS&2)?0:1);
        const int16_t cc=(int16_t)-cosineEvenNode(node);
#elif LPX4_COMPACT_ONLY
        const int16_t cc=(int16_t)-cosineInterpolate(lpx4LsfNorm10(
            centeredLsf(LPX4_PREVIOUS_BINS[i],LPX4_SPEECH_FLAGS),centeredLsf(cur_[i],LPX4_SPEECH_FLAGS),t));
#else
        const int16_t cc=(int16_t)-cosineInterpolate(lpx4LsfNorm10(LPX4_PREVIOUS_BINS[i],cur_[i],t));
#endif
        // P/Q polynomials are independent; each pair retains the same degree.
#if LPX4_MEMORY_PROFILE == LPX4_MEMORY_PROFILE_SRAM512
        const uint8_t base=(i&1)?qbase:pbase;
#if LPX4_POLY24_WORKSPACE
        ringPolyFactor(ringQ_,base,cc,(uint8_t)((i&254)+2),!(i&1));
#else
        if(i<2){
            const int16_t unit=(i&1)?-4096:4096;
            // |cc|<=8192, so the shared first coefficient fits signed16.
            // P2=P1 and Q2=-Q1 for these exact initial unit factors.
            const int16_t first=unit+cc;
            ringPolyPut(ringQ_,base,1,first);
            ringPolyPut(ringQ_,base,2,(i&1)?-(int32_t)first:(int32_t)first);
            ringPolyPut(ringQ_,base,3,unit);
        }else ringPolyFactor(ringQ_,base,cc,(uint8_t)((i&254)+2),halfPolynomialP&&!(i&1));
#endif
#else
        int32_t* p=(i&1)?polyQ_:polyP_;
        if(i<2){
            // Exact (1 +/- z) first factors; no rounded multiplication.
            const int16_t unit=(i&1)?-4096:4096;
            p[1]=unit+cc;p[2]=4096+((i&1)?-cc:cc);p[3]=unit;
        }else polyFactor(p,cc,(uint8_t)((i&254)+2));
#endif
    }
#if LPX4_MEMORY_PROFILE == LPX4_MEMORY_PROFILE_SRAM512
#if LPX4_POLY24_WORKSPACE
    // Mirror P at the middle pair. Q remains forward throughout.
    uint8_t pOffset=pbase+4,qOffset=qbase+4;
    uint8_t pStep=4;
#endif
    for(uint8_t i=0;i<10;i++){
#if LPX4_POLY24_WORKSPACE
#if LPX4_PLAYER_PITCH_PAGE
        // Both coefficients are in the same aligned SRAM page. Reuse ZH
        // and consume the second coefficient a byte at a time.
        const int8_t* address=pitchRingAddress(ringQ_,pOffset);
        PolyCoefficient sum;
        uint8_t part;
        __asm__("ld %A0,Z\n\tldd %B0,Z+1\n\tldd %C0,Z+2\n\t"
                "mov %A1,%3\n\t"
                "ld %2,Z\n\tadd %A0,%2\n\t"
                "ldd %2,Z+1\n\tadc %B0,%2\n\t"
                "ldd %2,Z+2\n\tadc %C0,%2"
                : "=&r"(sum),"+&z"(address),"=&r"(part) : "r"(qOffset) : "cc","memory");
#else
        const PolyCoefficient sum=ringPolyLoad24(ringQ_,pOffset)+ringPolyLoad24(ringQ_,qOffset);
#endif
        out[i]=lpx4HalfClip15From24(sum);
        qOffset+=4;
        if(i==4)pStep=(uint8_t)-4;else pOffset+=pStep;
#else
        // Degree11 P[k] == P[11-k]; fixed-header images retain full P storage.
        const uint8_t pindex=halfPolynomialP?(i<5?i+1:10-i):i+1;
        const int32_t sum=ringPolyGet(ringQ_,pbase,pindex)+ringPolyGet(ringQ_,qbase,i+1);
        out[i]=clamp(truncShift(sum,1),-32767,32767);
#endif
    }
#else
    for(uint8_t i=0;i<10;i++)out[i]=clamp(truncShift(polyP_[i+1]+polyQ_[i+1],1),-32767,32767);
#endif
#endif // LPX4_FLOAT_SYNTHESIS
#undef LPX4_PREVIOUS_BINS
#endif

}
void Lpx4HybridCore::interpolateLsf(uint8_t sub){
#if LPX4_TINY_ANCHOR_PHASE
    Lpx4SynthesisValue* curLpc=lpcAnchors_;
#elif LPX4_ROTATE_LPC_ANCHORS
#if LPX4_V9_ROM_HEADER_LAYOUT
    auto* curLpc=reinterpret_cast<Lpx4SynthesisValue*>(
        reinterpret_cast<uint8_t*>(lpcAnchors_)+lpcAnchorOffset_);
#else
    Lpx4SynthesisValue* curLpc=lpcAnchors_+lpcAnchorOffset_;
#endif
#else
    Lpx4SynthesisValue* curLpc=curLpc_;
    Lpx4SynthesisValue* prevLpc=prevLpc_;
#endif
    // An unchanged LSF vector has identical polynomial anchors and no LPC
    // interpolation. The cached endpoint is valid across repeated frames.
    if(staticSpectrum_){
#if LPX4_AVR_V9_PACKETS && LPX4_ROTATE_LPC_ANCHORS && !defined(LPX3_BANDWIDTH_EXPAND_Q14)
        // Subframe zero has already primed the cache and copied the
        // endpoint. The other subframes of a static spectrum reuse it.
        if(sub)return;
#endif
        if(!lsfCached_){
            // The v9 packet path initializes from the current spectrum
            // without copying its bins to the previous spectrum.
            convertLsfAt(LPX4_AVR_V9_PACKETS?16:0,curLpc);
            lsfCached_=true;
        }
        // The endpoint is unchanged for the whole frame. Refresh a_ at its
        // first subframe, because the previous dynamic frame ended at a midpoint.
#if !LPX4_ROTATE_LPC_ANCHORS
        if(sub==0)for(uint8_t i=0;i<10;i++)prevLpc[i]=curLpc[i];
#endif
#ifdef LPX3_BANDWIDTH_EXPAND_Q14
        // nextCore expands a_ after interpolation: reload before every expansion.
        for(uint8_t i=0;i<10;i++)a_[i]=curLpc[i];
#else
        if(sub==0)for(uint8_t i=0;i<10;i++)a_[i]=curLpc[i];
#endif
        return;
    }
#if LPX4_TINY_ANCHOR_PHASE
#if LPX4_USE_AVR_NOMUL_ASM
    static_assert(sizeof(Lpx4SynthesisValue)==2,"LPC anchor stride is twenty bytes");
    Lpx4SynthesisValue* prevLpc=lpcAnchors_;
    __asm__("sbrs %2,2\n\tadiw %A0,20\n\t"
            "sbrc %2,2\n\tadiw %A1,20"
            : "+&w"(curLpc),"+&w"(prevLpc) : "r"(sub) : "cc");
#else
    Lpx4SynthesisValue* prevLpc=lpcAnchors_+10;
    if(!(sub&4)){
        prevLpc=lpcAnchors_;
        curLpc=lpcAnchors_+10;
    }
#endif
#elif LPX4_ROTATE_LPC_ANCHORS
#if LPX4_V9_ROM_HEADER_LAYOUT
    auto* prevLpc=reinterpret_cast<Lpx4SynthesisValue*>(
        reinterpret_cast<uint8_t*>(lpcAnchors_)+(lpcAnchorOffset_^(10*sizeof(Lpx4SynthesisValue))));
#else
    Lpx4SynthesisValue* prevLpc=lpcAnchors_+(lpcAnchorOffset_^10);
#endif
#endif
    // Segment width in t=0..16; at most one polynomial conversion per
    // 20-sample subframe after the initial frame (two at startup).
    const uint8_t width=(uint8_t)(16/LPX3_LPC_SEGMENTS);
    const uint8_t subframesPerSegment=(uint8_t)(8/LPX3_LPC_SEGMENTS);
#if LPX4_AVR25_LSF_ASM
    uint8_t localT;
#endif
    if(sub%subframesPerSegment==0){
#if LPX4_TINY_ANCHOR_PHASE
        // Pointer selection already follows the two-segment phase.
#elif LPX4_ROTATE_LPC_ANCHORS
#if !LPX4_AVR_V9_PACKETS
        if(sub==0&&!lsfCached_)convertLsfAt(0,prevLpc);
        else{
#endif
            // The shared v9 parser forces the first frame to be static.
            // Its initial endpoint is valid before dynamic interpolation.
            Lpx4SynthesisValue* scratch=prevLpc;prevLpc=curLpc;curLpc=scratch;
#if LPX4_V9_ROM_HEADER_LAYOUT
            lpcAnchorOffset_^=10*sizeof(Lpx4SynthesisValue);
#else
            lpcAnchorOffset_^=10;
#endif
#if !LPX4_AVR_V9_PACKETS
        }
#endif
#else
        if(sub==0){
            if(lsfCached_){
                // Last endpoint of prior frame was this frame's old LSF.
                for(uint8_t i=0;i<10;i++)prevLpc[i]=curLpc[i];
            }else convertLsfAt(0,prevLpc);
        }else{
            for(uint8_t i=0;i<10;i++)prevLpc[i]=curLpc[i];
        }
#endif
#if LPX4_TINY_ANCHOR_PHASE
        const uint8_t anchor=(sub&4)?16:8;
#else
        const uint8_t anchor=(uint8_t)(((sub/subframesPerSegment)+1)*width);
#endif
        convertLsfAt(anchor,curLpc);
#if !LPX4_AVR_V9_PACKETS || !LPX4_ROTATE_LPC_ANCHORS
        lsfCached_=true;
#endif
#if LPX4_AVR25_LSF_ASM
        // Segment starts are subframe0/4; their prepared odd half-phase is0.
        localT=0;
    }else localT=(uint8_t)(sub&3);
#else
    }
    const uint8_t t=(uint8_t)(sub*2+1);
    const uint8_t localT=(uint8_t)(t%width);
#endif
#if LPX4_USE_AVR_ASM && LPX4_COMPACT_VERSION==9
    const uint8_t phase=LPX3_LPC_SEGMENTS==2?(uint8_t)((sub&3)*64+32):(uint8_t)(localT*(256/width));
#endif
#if LPX4_USE_AVR_ASM && LPX4_COMPACT_VERSION==9
    lpx4LpcInterpolateVectorPrepared(a_,prevLpc,curLpc,phase);
#else
    for(uint8_t i=0;i<10;i++){
#if LPX4_FLOAT_SYNTHESIS
        a_[i]=prevLpc[i]+(curLpc[i]-prevLpc[i])*(static_cast<double>(localT)/width);
#elif LPX4_USE_AVR_ASM && LPX4_COMPACT_VERSION==9
        a_[i]=lpx4LpcInterpolatePrepared(prevLpc[i],curLpc[i],phase);
#else
        a_[i]=lpx4LpcInterpolate<LPX4_AVR25_V9_RUNTIME,LPX4_AVR25_LSF_ASM>(prevLpc[i],curLpc[i],localT,
            LPX3_LPC_SEGMENTS==1?4:LPX3_LPC_SEGMENTS==2?3:2);
#endif
    }
#endif

}

#if LPX4_AVR25_V9_RUNTIME
// Keep frame parsing and LPC interpolation out of the sample loop.
__attribute__((noinline))
#else
inline __attribute__((always_inline))
#endif
#if LPX4_AVR25_V9_RUNTIME && LPX4_V9_ROM_HEADER_LAYOUT && LPX3_LPC_SEGMENTS==2 && !defined(LPX4_ENABLE_PCM16)
// Keep the two-pointer converter's address expressions in their original
// form across this caller. AVR-GCC 7.3.0 then needs fewer saved registers.
__attribute__((optimize("no-tree-forwprop,no-tree-ter")))
#endif
bool Lpx4HybridCore::prepareSubframe(){
    // All frame/block/excitation headers coincide with a 20-sample boundary.
#if LPX4_COMPACT_ONLY
    if(!(subIndex_&7)&&!readFrame())return false;
#else
    if(subIndex_==0&&!readFrame())return false;
#endif
#if !LPX4_COMPACT_ONLY
    if(!(subIndex_&3)&&!readBlock())return false;
#endif
#if LPX4_AVR_V9_PACKETS
    // Dense pulse packets occur every other subframe. Sparse80 uses
    // every fourth, so test the second phase bit only for that profile.
    if(!(subIndex_&1) && (!(LPX4_SPEECH_FLAGS&8) || !(subIndex_&2)) && !readSubframe())return false;
#elif LPX4_HAS_SPARSE80
    if(!(subIndex_&((LPX4_SPEECH_FLAGS&8)?3:1))&&!readSubframe())return false;
#else
    if(!(subIndex_&1)&&!readSubframe())return false;
#endif
    interpolateLsf(
#if LPX4_COMPACT_ONLY
        subIndex_&7
#else
        subIndex_
#endif
    );
#ifdef LPX3_BANDWIDTH_EXPAND_Q14
    // Bandwidth expansion a[k] *= gamma^(k+1), once per 20 samples.
#if LPX4_FLOAT_SYNTHESIS
    double weight=1.0;
    for(uint8_t k=0;k<10;++k){
        weight*=static_cast<double>(LPX3_BANDWIDTH_EXPAND_Q14)/16384.0;
        a_[k]=lpx4FloatClamp(a_[k]*weight,-32767.0/4096.0,32767.0/4096.0);
    }
#else
    uint16_t weight=16384;
    for(uint8_t k=0;k<10;k++){
        weight=(uint16_t)(((int32_t)weight*LPX3_BANDWIDTH_EXPAND_Q14+8192)>>14);
        a_[k]=clamp(((int32_t)a_[k]*weight+8192)>>14,-32767,32767);
    }
#endif
#endif
    return true;
}

// AVR PWM firmware uses the direct sample path. The optional signed-output
// interface shares the same arithmetic, selected independently of memory I/O.
#if defined(__AVR__) && !defined(LPX4_ENABLE_PCM16)
bool Lpx4HybridCore::next(uint8_t& pcm){
#else
bool Lpx4HybridCore::nextCore(Lpx4SynthesisValue& postfilterQ14){
#endif
#if LPX4_BATCHED_REMAINING
    if(error_||subPos_==subEnd_){
#if LPX4_COMPACT_VERSION == 9
        // V9 stores only pulse packets touched by the declared sample count.
        // Validate EOF on the final false next(), outside the sample hot path.
#if LPX4_ROM_POINTER
        const bool trailing=bytes_!=0;
#else
        const bool trailing=cursor_!=bytes_;
#endif
        if(!error_ && (trailing||bitBuffer_))error_=CORRUPT_STREAM;
#endif
        return false;
    }
#else
    if(error_||!remaining_){
#if LPX4_COMPACT_VERSION == 9
#if LPX4_ROM_POINTER
        const bool trailing=bytes_!=0;
#else
        const bool trailing=cursor_!=bytes_;
#endif
        if(!error_ && (trailing||bitBuffer_))error_=CORRUPT_STREAM;
#endif
        return false;
    }
#endif
    if(subPos_==0 && !prepareSubframe())return false;
#if LPX4_AVR5_SAMPLE_LEAF
    const int32_t excitation=decodeCompactAvr5(reinterpret_cast<uint8_t*>(&blockStep_));
#else
    int8_t q=0;
#if LPX4_COMPACT_ONLY
#if (LPX4_FAST_EXCITATION&2) && !LPX4_AVR25_V9_RUNTIME && !LPX4_AVR25_V9_ROM_LAYOUT
    if(pulseIndex_>=pulseCount_){q=(int8_t)pitchPredict();LPX4_PITCH_RING_SAMPLE(ringQ_,ringCursor_++)=q;}
    else
#endif
    if(!decodeCode(q))return false;
#else
#if LPX4_FAST_EXCITATION
    bool simple=false;
    if((LPX4_FAST_EXCITATION&1) && subType_==0 && (!mode_ || !riceK_)){
        q=mode_?(int8_t)((int16_t)readBits(mode_)-quantLimit_):0;
        if(error_)return false;
        // A raw code is already within the validated source bit width.
        simple=true;
    }
#if LPX4_ALLOW_SPARSE
    else if((LPX4_FAST_EXCITATION&2) && subType_==2 && pulseIndex_>=pulseCount_){
        // No pulse remains: pitchPredict has already performed saturation.
        q=(int8_t)pitchPredict();simple=true;
    }
#endif
    else if((LPX4_FAST_EXCITATION&4) && subType_==1 && !riceK_ && bitsLeft_ && (bitBuffer_&1)){
        // Unary terminator1 with k0 is exactly delta0; consume only that bit.
        bitBuffer_>>=1;--bitsLeft_;
#ifdef LPX3_COST_INSTRUMENT
        ++bitCalls_;
#endif
        q=(int8_t)pitchPredict();simple=true;
    }
    if(simple)LPX4_PITCH_RING_SAMPLE(ringQ_,ringCursor_++)=q;
    else
#endif
    if(!decodeCode(q))return false;
#endif
#endif
#ifdef LPX3_Q_DIAG
    lastQ_=q;
#endif
#if LPX4_FLOAT_SYNTHESIS
    const double excitation=static_cast<double>(q)*blockStep_/(LPX4_EXCITATION_Q4?16.0:1.0);
    double pred=excitation;
#if LPX4_LPC_RING
    double* history=hist_+(subPos_<10?subPos_:subPos_-10)+10;
    for(uint8_t i=0;i<10;++i)pred-=a_[i]*history[-1-i];
    history-=10;
    pred=lpx4FloatClamp(pred,-32767.0,32767.0);
    history[0]=history[10]=pred;
#else
    for(int8_t i=9;i>=0;--i){
        pred-=a_[i]*hist_[i];
        if(kShiftHistorySpare || i<9)hist_[i+1]=hist_[i];
    }
    pred=lpx4FloatClamp(pred,-32767.0,32767.0);
    hist_[0]=pred;
#endif
#ifdef LPX4_FIXED_PRE_Q14
    const double pre=LPX4_FIXED_PRE_Q14/16384.0;
#else
    const double pre=preQ14_/16384.0;
#endif
#ifdef LPX4_FIXED_BRIGHT_Q14
    const double bright=LPX4_FIXED_BRIGHT_Q14/16384.0;
#else
    const double bright=brightQ14_/16384.0;
#endif
    const double prevBright=lpx4FloatClamp(prevDeemph_,-16384.0,16384.0);
    const double deemph=lpx4FloatClamp(pred+pre*prevDeemph_,-32767.0,32767.0);
    prevDeemph_=deemph;
    const double clipped=lpx4FloatClamp(deemph,-16384.0,16384.0);
    const double b=lpx4FloatClamp(clipped-bright*prevBright,-16384.0,16384.0);
#else
#if !LPX4_AVR5_SAMPLE_LEAF
    const uint16_t step=blockStep_;
#if LPX4_EXCITATION_Q4
    const int32_t excitation=lpx4Mul8xU16<LPX4_AVR25_V9_RUNTIME>(q,step);
#else
    // q is signed8 and the exact reconstructed step is 0..4016.
    const int32_t excitation=lpx4Excitation(q,step);
#endif
#endif
#if LPX4_LPC_RING
    // subPos already repeats every20 samples; no separate ring cursor is needed.
    int16_t* history=hist_+(subPos_<10?subPos_:subPos_-10)+10;
    int16_t pred=lpx4Clip15From24<LPX4_AVR25_V9_RUNTIME>(lpx4SynthesisRingQ12<LPX4_EXCITATION_Q4>(excitation,a_,history));
    history[0]=history[10]=pred;
#else
#if LPX4_AVR25_V9_RUNTIME
    int16_t* history;
    // LSF conversion clips both anchors to +/-32767 and interpolation stays between them.
    const int32_t synthesis=lpx4SynthesisQ12<LPX4_EXCITATION_Q4,true,true,true>(excitation,a_,hist_,&history);
    const int16_t pred=lpx4ClipSynthesisQ4(synthesis);
    *history=pred;
#elif LPX4_USE_AVR_ASM && LPX4_COMPACT_VERSION==9 && \
      LPX4_AVR_DOT_UNROLL==9 && LPX4_EXCITATION_Q4
    // The 20-sample subframe resets on a ten-slot history boundary.
    constexpr size_t historyOffset=offsetof(Lpx4HybridCore,hist_)-offsetof(Lpx4HybridCore,subPos_);
    static_assert(historyOffset<=63,"LPC history exceeds the AVR ADIW immediate");
    int16_t pred=lpx4SynthesisCircularQ12<historyOffset>(excitation,a_,&subPos_);
#else
    int16_t pred=lpx4Clip15From24<LPX4_AVR25_V9_RUNTIME>(lpx4SynthesisQ12<LPX4_EXCITATION_Q4,kShiftHistorySpare>(excitation,a_,hist_));
    hist_[0]=pred;
#endif
#endif
#if LPX4_USE_AVR_ASM && LPX4_COMPACT_VERSION==9 && LPX4_V9_ROM_HEADER_LAYOUT
    int16_t b=limitBrightnessOutput(lpx4PostfilterPair<offsetof(Lpx4HybridCore,prevDeemph_)-offsetof(Lpx4HybridCore,preQ14_)>(pred,(uint8_t*)&preQ14_));
#else
#if LPX4_AVR25_V9_PREPARED_ATTENUATION
    // Retain the old state across the arithmetic leaf for both filter passes.
    const int16_t previous=prevDeemph_;
    int16_t deemph=preQ14_?lpx4AddClip15<true>(pred,lpx4PreparedAttenuationQ14(previous,preQ14_)):pred;
#elif defined(LPX4_FIXED_PRE_Q14)
    int16_t deemph=LPX4_FIXED_PRE_Q14?lpx4AddClip15<LPX4_AVR25_V9_RUNTIME>(pred,lpx4AttenuateFixedQ14<LPX4_FIXED_PRE_Q14>(prevDeemph_)):pred;
#else
    int16_t deemph=preQ14_?lpx4AddClip15<LPX4_AVR25_V9_RUNTIME>(pred,lpx4AttenuateQ14(preQ14_,prevDeemph_)):pred;
#endif
    // Between samples, brightness history is exactly clipQ14(prevDeemph_).
    // Derive it before publishing the new deemphasis state.
#if !LPX4_AVR25_V9_PREPARED_ATTENUATION
    const int16_t prevBright=lpx4ClipQ14(prevDeemph_);
#endif
    prevDeemph_=deemph;
    int16_t clipped=lpx4ClipQ14(deemph);
    // Header validation limits brightness to11469; both clipped values are
    // +/-16384. The un-clipped difference is within +/-27853, signed16-safe.
#if LPX4_AVR25_V9_PREPARED_ATTENUATION
    int16_t b=brightQ14_?limitBrightnessOutput((int16_t)(clipped-lpx4PreparedAttenuationQ14(lpx4ClipQ14(previous),brightQ14_))):clipped;
#elif defined(LPX4_FIXED_BRIGHT_Q14)
    int16_t b=LPX4_FIXED_BRIGHT_Q14?lpx4ClipQ14((int16_t)(clipped-lpx4AttenuateFixedQ14<LPX4_FIXED_BRIGHT_Q14>(prevBright))):clipped;
#else
    int16_t b=brightQ14_?limitBrightnessOutput((int16_t)(clipped-lpx4AttenuateQ14(brightQ14_,prevBright))):clipped;
#endif
#endif
#endif
    // Preserve the postfilter signal before final output conversion. Floating
    // mode retains fractional precision; fixed mode retains integer Q14.
#if defined(__AVR__) && !defined(LPX4_ENABLE_PCM16)
    // Original PWM transfer function for the existing ATmega328P firmware.
#if LPX4_PWM_ROUND
#if (LPX4_AVR25_V9_RUNTIME || (LPX4_USE_AVR_ASM && LPX4_COMPACT_VERSION==9)) && LPX4_PWM_GAIN==130
    pcm=lpx4PwmBounded130(b);
#else
    pcm=lpx4PwmQ14(b,LPX4_PWM_GAIN);
#endif
#else
    int16_t duty=(int16_t)(128+((int32_t)b*LPX4_PWM_GAIN)/16384);
    pcm=(uint8_t)clamp(duty,0,255);
#endif
#else
    postfilterQ14 = b;
#endif
#if !LPX4_BATCHED_REMAINING
    --remaining_;
#endif
    ++subPos_;
#if LPX4_HAS_SPARSE80 && LPX4_COMPACT_VERSION != 9
    // Validate all stored last-packet pulse fields even for a partial tail.
    // This consumes input padding only, without producing extra samples.
    if((LPX4_SPEECH_FLAGS&8) &&
#if LPX4_BATCHED_REMAINING
       remaining_<=20 && subPos_==remaining_){
#else
       !remaining_){
#endif
        const uint16_t tail=(uint16_t)sampleCount_%320u;
        uint8_t unread=tail?(uint16_t)(320u-tail)/80u:0;
        while(unread--)readBits(7);
#if LPX4_ROM_POINTER
        const bool trailing=bytes_!=0;
#else
        const bool trailing=cursor_!=bytes_;
#endif
        if(error_||trailing||bitBuffer_){error_=CORRUPT_STREAM;return false;}
    }
#endif
    if(subPos_==20){
        subPos_=0;
#if LPX4_BATCHED_REMAINING
        remaining_-=20;
        subEnd_=remaining_<20?(uint8_t)remaining_:20;
#endif
#if LPX4_AVR_V9_PACKETS
        // Consumers use only the low four bits. Unsigned wrap is harmless.
        ++subIndex_;
#elif LPX4_COMPACT_ONLY
        subIndex_=(subIndex_&8)|((subIndex_+1)&7);
#else
        if(++subIndex_==8)subIndex_=0;
#endif
#if LPX4_ENABLE_SPEECH_COMPACT && LPX4_COMPACT_VERSION != 9
        // A complete final packet must consume the declared payload, with
        // only zero bits left in its final byte. The subframe index also has
        // to wrap: second-half partial tails still have stored pulse fields.
        // Partial sample tails retain
        // the documented unconsumed-padding behavior.
#if LPX4_COMPACT_ONLY
        if(!remaining_ && !subIndex_){
#else
        if(speechCompact_ && !remaining_ && !speechHalf_ && !subIndex_){
#endif
#if LPX4_ROM_POINTER
            const bool trailing=bytes_!=0;
#else
            const bool trailing=cursor_!=bytes_;
#endif
            if(trailing || bitBuffer_){error_=CORRUPT_STREAM;return false;}
        }
#endif
    }
    return true;
}

// Legacy 8-bit output retained for unchanged AVR/Arduino playback.
#if !defined(__AVR__) || defined(LPX4_ENABLE_PCM16)
bool Lpx4HybridCore::next(uint8_t& pcm){
    Lpx4SynthesisValue b;
    if(!nextCore(b))return false;
#if LPX4_FLOAT_SYNTHESIS
    pcm=lpx4FloatPwm(b,LPX4_PWM_GAIN,LPX4_PWM_ROUND!=0);
#elif LPX4_PWM_ROUND
    pcm=lpx4PwmQ14(b,LPX4_PWM_GAIN);
#else
    const int16_t duty=(int16_t)(128+((int32_t)b*LPX4_PWM_GAIN)/16384);
    pcm=(uint8_t)clamp(duty,0,255);
#endif
    return true;
}

// Raw signed signal after LPC synthesis, deemphasis and brightness filter,
// nominal Q14, valid range -16384..+16384. Bypasses PWM completely.
// Only enable these additional output functions on AVR when explicitly needed;
// the usual PWM firmware retains its old size/cost requirements.
bool Lpx4HybridCore::nextQ14(int16_t& out){
#if LPX4_FLOAT_SYNTHESIS
    double b;if(!nextCore(b))return false;
    out=lpx4FloatQuantize(b,-16384,16384);return true;
#else
    return nextCore(out);
#endif
}

// Signed full-scale linear PCM16 for comparison against reference PCM16 WAV.
// No gain fitting or truncation to 8 bits. +16384 maps to +32767 (saturation),
// -16384 to -32768; input waveform is compared against WAV /32768.0.
bool Lpx4HybridCore::nextS16(int16_t& out){
    Lpx4SynthesisValue b;
    if(!nextCore(b))return false;
#if LPX4_FLOAT_SYNTHESIS
    out=lpx4FloatQuantize(b*2.0,-32768,32767);
#else
    out=clamp((int32_t)b*2,-32768,32767);
#endif
    return true;
}
#endif

#if LPX4_FLOAT_SYNTHESIS
bool Lpx4HybridCore::nextFloat(double& out){
    double b;if(!nextCore(b))return false;
    out=b/16384.0;return true;
}
#endif
