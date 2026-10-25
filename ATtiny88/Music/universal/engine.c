/* UM88 v1. The compiled code is identical for every composition. */
#include "engine.h"
#include "storage.h"
#include <string.h>
#if defined(__GNUC__)
#define UM_NOINLINE __attribute__((noinline))
#else
#define UM_NOINLINE
#endif
UMState um;
uint16_t um_normalizer;
int8_t um_normalizerMin;
uint8_t um_masterShift;
uint8_t um_channels;
static uint16_t waveTable,contextTable,envelopeTable,ruleTable,rowTable,pitchTable;
static uint8_t levelDirty,contextDirty;
#ifndef UM_COMPACT_SCORE_ONLY
#define UM_COMPACT_SCORE_ONLY 0
#endif
static uint16_t literalCount;
static uint8_t streamBit;
#if !UM_COMPACT_SCORE_ONLY
static uint8_t packedSymbols;
#endif
/* Header: UM88, voices, channels, master shift, normalizer minimum;
   then pointers: waves, contexts, envelopes, rules, stream, alphabet, normalizer. */
#define FIELD(offset) UM_READ(UM_SONG_ADDRESS+(offset))
#define POINTER(offset) um_word(UM_SONG_ADDRESS+(offset))
/* Share header binding instead of expanding a Flash word read per pointer. */
static UM_NOINLINE void bind_pointer(uint16_t *target,uint8_t offset) {
    *target=POINTER(offset);
}
static UM_NOINLINE uint16_t read9(uint16_t at,uint8_t shift) {
    return (um_word(at)>>shift)&511;
}

static uint16_t symbol(void) {
#if !UM_COMPACT_SCORE_ONLY
    if(!packedSymbols){
    uint16_t stream=um.stream;
    uint8_t first=UM_READ(stream++);
    uint16_t value=first;
    if(first>=128)value=((uint16_t)(first&127)<<8)|UM_READ(stream++);
    um.stream=stream;
    return value;
    }
#endif
    uint16_t stream=um.stream;
    uint8_t bit=streamBit;
    uint16_t code=read9(stream,bit);
    bit++;
    um.stream=stream+1+(bit>>3);streamBit=bit&7;
    return code;
}
static uint8_t command(void) {
    uint16_t *pending=um.pending+um.depth;
    uint16_t code=um.depth?*--pending:symbol();
    while(code>=literalCount){
#if !UM_COMPACT_SCORE_ONLY
        if(!packedSymbols){
        uint16_t at=ruleTable+((code-256)<<2);
        *pending++=um_word(at+2);
        code=um_word(at);
        }else
#endif
        {
            /* Each pair occupies 18 bits. Pair starts have shifts 0,2,4,6;
               the right symbol always starts in the following byte. */
            uint16_t index=code-literalCount;
            uint16_t at=ruleTable+(index<<1)+(index>>2);
            uint8_t shift=(index&3)<<1;
            *pending++=read9(at+1,shift+1);
            code=read9(at,shift);
        }
    }
    um.depth=pending-um.pending;
#if !UM_COMPACT_SCORE_ONLY
    if(!packedSymbols)return (uint8_t)code;
#endif
    return UM_READ(ruleTable-literalCount+code);
}
/* Pure arithmetic: signed sample times a four-bit level. The intermediate
 * fits int16_t; addition avoids undefined left shifts of negative values. */
#if defined(__GNUC__)
static __attribute__((always_inline)) inline
#else
static inline
#endif
int16_t um_gain_product(int8_t value,uint8_t level) {
    int16_t term=value,product=0;
    if(level&1)product=term;
    term+=term;if(level&2)product+=term;
    term+=term;if(level&4)product+=term;
    term+=term;if(level&8)product+=term;
    return product;
}
#if !defined(__AVR_ATtiny88__) || !defined(UM_ENABLE_AVR_ASM) || !UM_ENABLE_AVR_ASM
void um_scale_wave(uint16_t source,int8_t *target,uint8_t level,uint8_t gain) {
    for(uint8_t i=0;i<8;i++){
        uint8_t packed=UM_READ(source++);
        for(uint8_t half=0;half<2;half++,packed>>=4){
            uint8_t nibble=packed&15;
            int8_t value=(gain&32)?(int8_t)nibble-8:(int8_t)(um_gain_product((int8_t)nibble-8,level));
            *target++=value>>(gain&7);
        }
    }
}
#endif
static void refresh(UMVoice *v) {
    uint16_t context=contextTable+((uint16_t)v->context<<2);
    uint8_t bank=UM_READ(context+1),gain=UM_READ(context+2),level=v->level;
    v->mix=UM_READ(context+3);
    if((gain&64)&&level>=14)bank|=48;
    if(gain&128)level>>=1;
    if(gain&16)level>>=1;
    um_scale_wave(waveTable+bank,v->wave,level,gain);
}
/* Flash offsets remove repeated software multiplies on AVR25. sizeof keeps
 * the portable layout; larger records retain ordinary pointer arithmetic. */
static const uint8_t voice_offsets[UM_VOICES] UM_CONST={
    (uint8_t)(0*sizeof(UMVoice)),(uint8_t)(1*sizeof(UMVoice)),
    (uint8_t)(2*sizeof(UMVoice)),(uint8_t)(3*sizeof(UMVoice)),
    (uint8_t)(4*sizeof(UMVoice)),(uint8_t)(5*sizeof(UMVoice)),
    (uint8_t)(6*sizeof(UMVoice)),(uint8_t)(7*sizeof(UMVoice))};
static UM_NOINLINE UMVoice *voice_at(uint8_t index) {
    if((UM_VOICES-1)*sizeof(UMVoice)<=255)
        return (UMVoice *)((uint8_t *)um.voice+UM_VALUE(voice_offsets,index));
    return &um.voice[index];
}
static UM_NOINLINE void restart_stream(void) {
    bind_pointer(&um.stream,16);streamBit=0;um.depth=0;um.ticks=0;um.tickPhase=0;
    um.drumMode=0;um.drumPhase=0;um.noiseHigh=1;
    contextDirty=255;
}
static UM_NOINLINE void mark_dirty(uint8_t *flags,uint8_t index) {*flags|=(uint8_t)1<<index;}
static void read_events(void) {
    for(;;){
        uint8_t op=command(),index=op&7;
        if(op==0){
            for(uint8_t i=0;i<um.count;i++){
                um.voice[i].phase=0;um.voice[i].step=0;um.voice[i].level=0;
            }
            restart_stream();
            continue;
        }
        if(op<64){um.wait=op;return;}
        if(op>=128)index=(op>>4)&7;
        UMVoice *v=voice_at(index);
        if(op<72){uint8_t context=command();if(v->context!=context)mark_dirty(&contextDirty,index);v->context=context;}
        else if(op<80)v->step=um_word(pitchTable+((uint16_t)command()<<1));
        else if(op<88)v->phase=0;
        else if(op<96)v->phase=voice_at(command())->phase;
        else if(op==96)um.drumMode=command();
        else if(op==97)um.drumPhase=command();
        else if(op==98)um.noiseHigh=command();
        else if(op>=128){uint8_t level=op&15;
            if(v->level!=level)mark_dirty(&levelDirty,index);
            v->level=level;}
    }
}
void um_init(void) {
    memset(&um,0,sizeof um);
    um.count=FIELD(4);um_channels=FIELD(5);
    bind_pointer(&waveTable,8);bind_pointer(&contextTable,10);bind_pointer(&envelopeTable,12);
    bind_pointer(&ruleTable,14);bind_pointer(&rowTable,18);bind_pointer(&pitchTable,24);
    literalCount=FIELD(23);if(!literalCount)literalCount=256;
#if !UM_COMPACT_SCORE_ONLY
    packedSymbols=FIELD(22);
#endif
    bind_pointer(&um_normalizer,20);um_normalizerMin=FIELD(7);um_masterShift=FIELD(6);
    restart_stream();read_events();
    UMVoice *voice=um.voice;
    for(uint8_t left=um.count;left;left--,voice++)refresh(voice);
}
/* Exact pointer traversal and one transition mask per tick. Adapted from
   docs/avr-asm-cookbook/examples/um88-tick-pointer.c.inc (d7c003d).
   Preserve envelope-before-event ordering and the portable state interface. */
void um_tick(void) {
    um.ticks++;um.tickPhase=(um.tickPhase+1)&15;
    levelDirty=0;contextDirty=0;
    uint8_t bit=1;
    const uint16_t mask=(uint16_t)1<<um.tickPhase;
    UMVoice *v=um.voice;
    for(uint8_t remaining=um.count;remaining;remaining--,v++,bit<<=1){
        uint8_t model=UM_READ(contextTable+((uint16_t)v->context<<2));
        uint8_t row=UM_READ(envelopeTable+((uint16_t)model<<4)+v->level);
        uint16_t at=rowTable+((uint16_t)row<<1)+row;
        if(um_word(at+1)&mask){
            uint8_t level=UM_READ(at);if(v->level!=level)levelDirty|=bit;v->level=level;
        }
    }
    if(!--um.wait)read_events();
    bit=1;v=um.voice;
    for(uint8_t remaining=um.count;remaining;remaining--,v++,bit<<=1){
        if((contextDirty&bit) || ((levelDirty&bit) && (v->mix&160)==128))refresh(v);
    }
}

#if !defined(__AVR_ATtiny88__) || !defined(UM_ENABLE_AVR_ASM) || !UM_ENABLE_AVR_ASM
uint32_t um_render(void) {
    int16_t l=0,r=0,group=0;
    UMVoice *v=um.voice;
    for(uint8_t remaining=um.count;remaining;remaining--,v++){
        v->phase+=v->step;
        group+=v->wave[v->phase>>12];
        uint8_t mix=v->mix;
        if(mix&128){
            int16_t value;
            if(mix&32){
                value=um_gain_product((int8_t)group,v->level)>>3;
                value>>=mix&1;
            }else value=group>>(mix&7);
            group=0;
            l+=(mix&8)?value>>1:value;
            r+=(mix&16)?value>>1:value;
        }
    }
    return (uint16_t)l|((uint32_t)(uint16_t)r<<16);
}
#endif
uint8_t um_output(int16_t value) {
    if(um_normalizer)return UM_READ(um_normalizer+(uint8_t)(value-um_normalizerMin));
    value*=1<<um_masterShift;value+=128;
    if(value<0)return 0;
    if(value>255)return 255;
    return value;
}
