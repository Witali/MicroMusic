// One-shot AVR player. Device registers come from the selected vendor header.
#include <avr/io.h>
#include <avr/interrupt.h>
#include <avr/pgmspace.h>
#include <util/atomic.h>
#include "Lpx4HybridCore.h"
#include "Lpx4Math.h"
#include "../../../../common/pwm_gain.h"
#if !defined(__AVR_ATtiny88__) && !defined(__AVR_ATmega328__) && !defined(__AVR_ATmega328P__)
#error Select ATtiny88, ATmega328 or ATmega328P with -mmcu
#endif
#if F_CPU != 16000000UL
#error This playback clock requires 16 MHz
#endif
#ifndef LPX25_QUEUE
#define LPX25_QUEUE 32
#endif
#ifndef LPX25_REPEAT
#define LPX25_REPEAT 1
#endif
#ifndef LPX25_GPIOR_STATE
// The dedicated v9 ROM player owns these three general-purpose registers.
// Arithmetic and ISR backends can each be selected independently.
#define LPX25_GPIOR_STATE LPX4_V9_ROM_HEADER_LAYOUT
#endif
#if LPX25_GPIOR_STATE != 0 && LPX25_GPIOR_STATE != 1
#error LPX25_GPIOR_STATE must be 0 or 1
#endif
#if LPX25_GPIOR_STATE && (!defined(GPIOR0) || !defined(GPIOR1) || !defined(GPIOR2))
#error The selected player hardware needs the vendor GPIOR register definitions
#endif
#ifndef LPX25_REUSE_TIMER1_HIGH
#define LPX25_REUSE_TIMER1_HIGH 0
#endif
#ifndef LPX25_ROM_OUTPUT_GAIN
#define LPX25_ROM_OUTPUT_GAIN 0
#endif
#if LPX25_ROM_OUTPUT_GAIN != 0 && LPX25_ROM_OUTPUT_GAIN != 1
#error LPX25_ROM_OUTPUT_GAIN must be 0 or 1
#endif
#if LPX25_REUSE_TIMER1_HIGH != 0 && LPX25_REUSE_TIMER1_HIGH != 1
#error LPX25_REUSE_TIMER1_HIGH must be 0 or 1
#endif
#if LPX25_QUEUE != 16 && LPX25_QUEUE != 24 && LPX25_QUEUE != 32 && LPX25_QUEUE != 44
#error Select a 16, 24, 32 or 44 byte queue
#endif
#if LPX25_REPEAT < 1 || LPX25_REPEAT > 255
#error Repeat count must be 1..255
#endif
#if LPX4_USE_AVR_NOMUL_ASM && LPX4_COMPACT_ONLY && LPX4_COMPACT_VERSION == 9 && !defined(LPX4_FIXED_SPEECH_FLAGS)
#define LPX25_V9_RUNTIME 1
#else
#define LPX25_V9_RUNTIME 0
#endif
#if LPX25_V9_RUNTIME || (LPX4_USE_AVR_ASM && LPX4_V9_ROM_HEADER_LAYOUT && LPX4_PLAYER_PITCH_PAGE)
#define LPX25_V9_ROM_PLAYER 1
#else
#define LPX25_V9_ROM_PLAYER 0
#endif
#if LPX25_V9_ROM_PLAYER && LPX4_V9_ROM_HEADER_LAYOUT && LPX25_REPEAT == 1 && \
    !LPX4_ENABLE_INPUT_CALLBACK && !defined(LPX4_ENABLE_PCM16)
#define LPX25_ALIAS_ERROR 1
#else
#define LPX25_ALIAS_ERROR 0
#endif
static const uint8_t voice[] PROGMEM={
#include "audio.inc"
#if LPX25_ROM_OUTPUT_GAIN
#include "output_gain.inc"
#endif
};
#if LPX25_ROM_OUTPUT_GAIN
// The byte after the LPX file belongs to the ROM playback configuration.
// Keep the LPX stream length and wire format unchanged for other decoders.
static uint8_t playbackGain(uint8_t sample){
    const uint8_t gain=pgm_read_byte(voice+sizeof(voice)-1);
#if LPX4_USE_AVR_NOMUL_ASM
    // Unity is the centered duty itself. Multiply by twice the remaining
    // Q7 numerator, then use the high byte and the low byte's sign bit for
    // the signed correction and rounding. Saturate on signed addition overflow.
    uint8_t centered=sample^128, productLow, productHigh, count;
    const uint8_t fraction=(uint8_t)(gain<<1);
    __asm__(
        "mov %1,%4\n\tclr %2\n\tldi %3,8\n\tlsr %1\n\t"
        "1: brcc 2f\n\tadd %2,%0\n\t"
        "2: ror %2\n\tror %1\n\tdec %3\n\tbrne 1b\n\t"
        "sbrc %0,7\n\tsub %2,%4\n\tlsl %1\n\tadc %2,__zero_reg__\n\t"
        "add %0,%2\n\tbrvc 4f\n\tldi %2,127\n\tsbrs %0,7\n\tinc %2\n\tmov %0,%2\n\t4:"
        : "+&r"(centered),"=&r"(productLow),"=&d"(productHigh),"=&d"(count)
        : "r"(fraction) : "cc");
    return centered^128;
#else
    const uint16_t scaled=((uint16_t)sample*gain+64)>>7;
    const int16_t duty=(int16_t)scaled+128-gain;
    return duty<0 ? 0 : duty>255 ? 255 : (uint8_t)duty;
#endif
}
#endif
#if LPX25_V9_ROM_PLAYER
// Static storage is cleared by startup. A normal begin() still resets
// the stream, including when this build requests repeat playback.
struct Lpx4RomPlayer {
    static Lpx4HybridCore decoder;
#if LPX25_ALIAS_ERROR
    static inline void materializeError(){
        // Keep the aliased byte observable when LTO folds a failed begin().
        __asm__ __volatile__("" : : "m"(decoder.error_) : "memory");
    }
    static inline void publishErrorAlias(){
        __asm__ __volatile__(
          ".global lpx25_error\n\t.type lpx25_error,@object\n\t"
          ".set lpx25_error,%0+%1\n\t.size lpx25_error,1"
          : : "i"(&decoder),"n"(__builtin_offsetof(Lpx4HybridCore,error_)) : "memory");
    }
#endif
#if LPX4_BATCHED_REMAINING
    // Called after next() succeeds, with parser errors already excluded.
    static bool sampleWasLast(){return decoder.subPos_==decoder.subEnd_;}
#endif
#if LPX4_V9_ROM_HEADER_LAYOUT && LPX25_REPEAT == 1
    static bool begin(){
#if LPX25_ALIAS_ERROR
        publishErrorAlias();
#endif
#if LPX25_ROM_OUTPUT_GAIN
        return decoder.beginRom(voice,sizeof(voice)-1,false);
#else
        return decoder.beginRom(voice,sizeof(voice),false);
#endif
    }
#endif
};
Lpx4HybridCore Lpx4RomPlayer::decoder{Lpx4HybridCore::StaticZeroInit{}};
static Lpx4HybridCore& decoder=Lpx4RomPlayer::decoder;
#else
static Lpx4HybridCore decoder;
#endif
extern "C" {
// Retain OR addressing for power-of-two rings. A 24-byte array needs only
// byte alignment: 32-byte alignment would pad its ELF section back to 32.
uint8_t lpx25_queue[LPX25_QUEUE] __attribute__((used,externally_visible,aligned(LPX25_QUEUE==24||LPX25_QUEUE==44?1:LPX25_QUEUE)));
#if LPX25_V9_ROM_PLAYER
#if !LPX25_GPIOR_STATE
volatile uint8_t lpx25_head,lpx25_tail,lpx25_stopped;
#endif
#if LPX25_ALIAS_ERROR
extern volatile uint8_t lpx25_error;
#else
volatile uint8_t lpx25_error;
#endif
// GNU AVR ld puts linkonce BSS after regular BSS. Keep this byte
// after the aligned queue to avoid adding an alignment gap.
volatile uint8_t lpx25_eof __attribute__((section(".gnu.linkonce.b.lpx25_eof")));
#else
#if LPX25_GPIOR_STATE
volatile uint8_t lpx25_eof,lpx25_error;
#else
volatile uint8_t lpx25_head,lpx25_tail,lpx25_eof,lpx25_stopped,lpx25_error;
#endif
#endif
}
#if LPX25_GPIOR_STATE
#define lpx25_head GPIOR0
#define lpx25_tail GPIOR1
#define lpx25_stopped GPIOR2
static inline void initializePlayerRegisters(){
    __asm__ __volatile__(
        ".global lpx25_head\n\t.type lpx25_head,@object\n\t"
        ".set lpx25_head,%[head_mem]\n\t.size lpx25_head,1\n\t"
        ".global lpx25_tail\n\t.type lpx25_tail,@object\n\t"
        ".set lpx25_tail,%[tail_mem]\n\t.size lpx25_tail,1\n\t"
        ".global lpx25_stopped\n\t.type lpx25_stopped,@object\n\t"
        ".set lpx25_stopped,%[stopped_mem]\n\t.size lpx25_stopped,1"
        : : [head_mem]"n"(_SFR_MEM_ADDR(GPIOR0)),[tail_mem]"n"(_SFR_MEM_ADDR(GPIOR1)),
            [stopped_mem]"n"(_SFR_MEM_ADDR(GPIOR2)) : "memory");
    lpx25_head=0;
    lpx25_tail=0;
    lpx25_stopped=0;
}
#endif
#if LPX25_ALIAS_ERROR
#define LPX25_REPORT_ERROR() Lpx4RomPlayer::materializeError()
#else
#define LPX25_REPORT_ERROR() (lpx25_error=decoder.error())
#endif
static inline void barrier(){__asm__ __volatile__("" ::: "memory");}
static inline uint8_t advance(uint8_t at){
#if LPX25_QUEUE == 24 || LPX25_QUEUE == 44
    return ++at==LPX25_QUEUE?0:at;
#else
    return (at+1)&(LPX25_QUEUE-1);
#endif
}
static void stop(){
    TCCR0A=0;
#if defined(TCCR0B)
    TCCR0B=0;
#endif
    TIMSK0=0;
    lpx25_stopped=1;
}
#ifndef LPX25_ENABLE_ASM_ISR
#define LPX25_ENABLE_ASM_ISR 0
#endif
#if LPX25_ENABLE_ASM_ISR && defined(__AVR_ARCH__) && \
    (__AVR_ARCH__==25 || (__AVR_ARCH__==5 && LPX25_REUSE_TIMER1_HIGH))
#ifndef LPX25_ISR_FIXED_REGS
#error The reserved-register ISR requires the matching whole-program -ffixed flags
#endif
#if defined(LPX25_IRQ_REGISTER_MAP)
#define LPX25_IRQ_SAMPLE "lpx25_irq_sample"
#define LPX25_IRQ_SREG "lpx25_irq_sreg"
#elif __AVR_ARCH__==5
// The AVR5 arithmetic backend uses r2 explicitly in signed products.
#define LPX25_IRQ_SAMPLE "r4"
#define LPX25_IRQ_SREG "r5"
#else
#define LPX25_IRQ_SAMPLE "r2"
#define LPX25_IRQ_SREG "r3"
#endif
ISR(TIMER0_COMPA_vect,ISR_NAKED){
    // The scratch pair is excluded from every foreground compilation. Z is a
    // normal foreground pointer and is preserved. The AVR5 path writes only
    // OCR1AL so it can preserve r0/r1 without using the MUL scratch registers.
    __asm__ __volatile__(
#if defined(LPX25_IRQ_REGISTER_MAP)
        ".include \"" LPX25_IRQ_REGISTER_MAP "\"\n\t"
#endif
        "in " LPX25_IRQ_SREG ",%0\n\tpush r30\n\tpush r31\n\t"
#if LPX25_GPIOR_STATE
        "in " LPX25_IRQ_SAMPLE ",%[head_io]\n\tin r30,%[tail_io]\n\t"
#else
        "lds " LPX25_IRQ_SAMPLE ",lpx25_head\n\tlds r30,lpx25_tail\n\t"
#endif
        "cp " LPX25_IRQ_SAMPLE ",r30\n\tbreq 2f\n\t"
#if LPX25_QUEUE == 24 || LPX25_QUEUE == 44
        "ldi r31,0\n\tsubi r30,lo8(-(lpx25_queue))\n\tsbci r31,hi8(-(lpx25_queue))\n\t"
        "ld " LPX25_IRQ_SAMPLE ",Z\n\tsubi r30,lo8(lpx25_queue)\n\tinc r30\n\t"
        "cpi r30,%4\n\tbrlo 4f\n\tclr r30\n\t4:\n\t"
#else
        "ldi r31,hi8(lpx25_queue)\n\tori r30,lo8(lpx25_queue)\n\t"
        "ld " LPX25_IRQ_SAMPLE ",Z\n\tinc r30\n\tandi r30,%3\n\t"
#endif
#if LPX25_GPIOR_STATE
        "out %[tail_io],r30\n\trjmp 3f\n\t"
#else
        "sts lpx25_tail,r30\n\trjmp 3f\n\t"
#endif
        "2: ldi r30,128\n\tmov " LPX25_IRQ_SAMPLE ",r30\n\t"
        "3:\n\t"
#if !LPX25_REUSE_TIMER1_HIGH
        "sts %1,__zero_reg__\n\t"
#endif
        "sts %2," LPX25_IRQ_SAMPLE "\n\t"
        "pop r31\n\tpop r30\n\tout %0," LPX25_IRQ_SREG "\n\treti\n\t"
        : : "I"(_SFR_IO_ADDR(SREG)),"n"(_SFR_MEM_ADDR(OCR1AH)),"n"(_SFR_MEM_ADDR(OCR1AL)),
            "M"(LPX25_QUEUE==24||LPX25_QUEUE==44?31:LPX25_QUEUE-1),"M"(LPX25_QUEUE)
#if LPX25_GPIOR_STATE
            ,[head_io]"I"(_SFR_IO_ADDR(GPIOR0)),[tail_io]"I"(_SFR_IO_ADDR(GPIOR1))
#endif
            );
}
#undef LPX25_IRQ_SAMPLE
#undef LPX25_IRQ_SREG
#else
ISR(TIMER0_COMPA_vect){
    uint8_t sample=128;
    const uint8_t tail=lpx25_tail;
    if(tail!=lpx25_head){
        barrier();sample=lpx25_queue[tail];barrier();
        lpx25_tail=advance(tail);
    }
    OCR1A=sample;
}
#endif
#if LPX25_V9_ROM_PLAYER && LPX4_V9_ROM_HEADER_LAYOUT && LPX25_REPEAT == 1
static bool begin(){return Lpx4RomPlayer::begin();}
#else
#if LPX25_ROM_OUTPUT_GAIN
static bool begin(){return decoder.begin(voice,sizeof(voice)-1);}
#else
static bool begin(){return decoder.begin(voice,sizeof(voice));}
#endif
#endif
// Startup enters main with IRQs masked. This player never returns, so no
// caller registers need to remain saved under the foreground stack.
#if LPX25_V9_RUNTIME
__attribute__((OS_main))
#endif
#if LPX25_V9_ROM_PLAYER && LPX4_USE_AVR_ASM && LPX3_LPC_SEGMENTS==2
// Preserve word-sized state expressions in the AVR5 foreground loop.
__attribute__((optimize("no-split-wide-types,no-tree-ccp")))
#elif LPX25_V9_RUNTIME && LPX4_V9_ROM_HEADER_LAYOUT && LPX3_LPC_SEGMENTS==2
// Preserve the measured AVR25 foreground register allocation.
__attribute__((optimize("no-tree-dominator-opts,no-tree-ter")))
#endif
int main(){
    // Reset starts with interrupts masked. Keep the actual compiler CPU macros.
    CLKPR=_BV(CLKPCE);CLKPR=0;
#if LPX25_GPIOR_STATE
    initializePlayerRegisters();
#endif
    if(!begin()){LPX25_REPORT_ERROR();lpx25_stopped=1;for(;;){}}
    uint8_t repeats=LPX25_REPEAT;
    bool started=false;
    for(;;){
#if !LPX25_V9_ROM_PLAYER
        if(lpx25_eof){
            // The foreground has no decoding left. Drain, then stop within a
            // few cycles of the final ISR return, before the next 2000-cycle
            // deadline. This keeps terminal bookkeeping out of every ISR.
            while(lpx25_head!=lpx25_tail){}
            ATOMIC_BLOCK(ATOMIC_RESTORESTATE){stop();}
            for(;;){}
        }
#endif
        const uint8_t head=lpx25_head,next=advance(head);
        if(next==lpx25_tail)continue;
        // Single playback publishes EOF on its last sample and goes directly
        // to the drain. A restart is reachable only for a repeat build.
        if((!LPX25_V9_ROM_PLAYER || LPX25_REPEAT>1) && decoder.finished()){
            --repeats;
            if(!begin()){LPX25_REPORT_ERROR();break;}
        }
        uint8_t sample;
        // Zero-byte symbols delimit the actual production decode region for
        // an external observer. They add no firmware counters or instructions.
        __asm__ __volatile__(".global lpx25_decode_begin\nlpx25_decode_begin:" ::: "memory");
        const bool decoded=decoder.next(sample);
        __asm__ __volatile__(".global lpx25_decode_end\nlpx25_decode_end:" ::: "memory");
        if(!decoded){LPX25_REPORT_ERROR();break;}
#if LPX25_V9_ROM_PLAYER && LPX4_BATCHED_REMAINING
        const bool last=Lpx4RomPlayer::sampleWasLast() && repeats==1;
#else
        const bool last=decoder.finished() && repeats==1;
#endif
#if LPX25_ROM_OUTPUT_GAIN
        lpx25_queue[head]=playbackGain(sample);barrier();
#else
        lpx25_queue[head]=micromusic_pwm_gain(sample);barrier();
#endif
#if LPX25_V9_ROM_PLAYER
        // The barrier orders the sample before the byte store. Only
        // the producer writes head, and the ISR never reads EOF.
        lpx25_head=next;
#else
        ATOMIC_BLOCK(ATOMIC_RESTORESTATE){lpx25_head=next;if(last)lpx25_eof=1;}
#endif
        if(!started && (next==LPX25_QUEUE*3/4 || last)){
            // OC1A/PB1, fast 8-bit PWM at 62.5 kHz. Timer0 CTC /8 gives 8 kHz.
            DDRB|=_BV(PB1);OCR1A=128;
            TCCR1A=_BV(COM1A1)|_BV(WGM10);TCCR1B=_BV(WGM12)|_BV(CS10);
            OCR0A=249;TCNT0=0;TIFR0=_BV(OCF0A);TIMSK0=_BV(OCIE0A);
#if defined(TCCR0B)
            TCCR0A=_BV(WGM01);TCCR0B=_BV(CS01);
#else
            TCCR0A=_BV(CTC0)|_BV(CS01);
#endif
            started=true;sei();
        }
#if LPX25_V9_ROM_PLAYER
        if(last)break;
#endif
    }
#if LPX25_V9_ROM_PLAYER
    // Report the end of decoding before the ISR drains the valid prefix.
    lpx25_eof=1;
    if(started){while(lpx25_head!=lpx25_tail){}}
    ATOMIC_BLOCK(ATOMIC_RESTORESTATE){stop();}
#else
    // Reject a prefill error; drain an already running valid prefix.
    ATOMIC_BLOCK(ATOMIC_RESTORESTATE){
        lpx25_eof=1;
        if(!started || lpx25_head==lpx25_tail)stop();
    }
    if(started){while(lpx25_head!=lpx25_tail){};ATOMIC_BLOCK(ATOMIC_RESTORESTATE){stop();}}
#endif
    for(;;){}
}
