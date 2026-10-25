/* UM88 v1. The compiled code is identical for every composition. */
#include "engine.h"
#include "storage.h"
#include <string.h>
#include "gain-table.inc"
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
static uint16_t symbol(void) {
#if !UM_COMPACT_SCORE_ONLY
    if(!packedSymbols){
    uint8_t first=UM_READ(um.stream++);
    if(first<128)return first;
    return ((uint16_t)(first&127)<<8)|UM_READ(um.stream++);
    }
#endif
    uint16_t code=(um_word(um.stream)>>streamBit)&511;
    um.stream++;
    if(++streamBit==8){streamBit=0;um.stream++;}
    return code;
}
static uint8_t command(void) {
    uint16_t code=um.depth?um.pending[--um.depth]:symbol();
    while(code>=literalCount){
#if !UM_COMPACT_SCORE_ONLY
        if(!packedSymbols){
        uint16_t at=ruleTable+((code-256)<<2);
        um.pending[um.depth++]=um_word(at+2);
        code=um_word(at);
        }else
#endif
        {
            /* Each pair occupies 18 bits. Pair starts have shifts 0,2,4,6;
               the right symbol always starts in the following byte. */
            uint16_t bit=(code-literalCount)*9;
            uint16_t at=ruleTable+(bit>>2);
            uint8_t shift=(bit&3)<<1;
            uint8_t lo=UM_READ(at),middle=UM_READ(at+1),hi=UM_READ(at+2);
            um.pending[um.depth++]=((middle|((uint16_t)hi<<8))>>(shift+1))&511;
            code=((lo|((uint16_t)middle<<8))>>shift)&511;
        }
    }
#if !UM_COMPACT_SCORE_ONLY
    if(!packedSymbols)return (uint8_t)code;
#endif
    return UM_READ(ruleTable-literalCount+code);
}
#if !defined(__AVR_ATtiny88__) || !defined(UM_ENABLE_AVR_ASM) || !UM_ENABLE_AVR_ASM
void um_scale_wave(uint16_t source,int8_t *target,uint8_t level,uint8_t gain) {
    for(uint8_t i=0;i<8;i++){
        uint8_t packed=UM_READ(source++);
        for(uint8_t half=0;half<2;half++,packed>>=4){
            uint8_t nibble=packed&15;
            int8_t value=(gain&32)?(int8_t)nibble-8:(int8_t)UM_VALUE(um_amplitudes,((uint16_t)level<<4)+nibble);
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
static void read_events(void) {
    for(;;){
        uint8_t op=command(),index=op&7;
        UMVoice *v=&um.voice[index];
        if(op==0){
            for(uint8_t i=0;i<um.count;i++){
                um.voice[i].phase=0;um.voice[i].step=0;um.voice[i].level=0;
            }
            um.stream=POINTER(16);streamBit=0;um.depth=0;um.ticks=0;um.tickPhase=0;
            um.drumMode=0;um.drumPhase=0;um.noiseHigh=1;
            contextDirty=255;
            continue;
        }
        if(op<64){um.wait=op;return;}
        if(op<72){uint8_t context=command();if(v->context!=context)contextDirty|=(uint8_t)1<<index;v->context=context;}
        else if(op<80)v->step=um_word(pitchTable+((uint16_t)command()<<1));
        else if(op<88)v->phase=0;
        else if(op<96)v->phase=um.voice[command()].phase;
        else if(op==96)um.drumMode=command();
        else if(op==97)um.drumPhase=command();
        else if(op==98)um.noiseHigh=command();
        else if(op>=128){index=(op>>4)&7;uint8_t level=op&15;
            if(um.voice[index].level!=level)levelDirty|=(uint8_t)1<<index;
            um.voice[index].level=level;}
    }
}
void um_init(void) {
    memset(&um,0,sizeof um);
    um.count=FIELD(4);um_channels=FIELD(5);um.stream=POINTER(16);um.noiseHigh=1;
    waveTable=POINTER(8);contextTable=POINTER(10);envelopeTable=POINTER(12);
    ruleTable=POINTER(14);rowTable=POINTER(18);pitchTable=POINTER(24);
    literalCount=FIELD(23);if(!literalCount)literalCount=256;
    streamBit=0;
#if !UM_COMPACT_SCORE_ONLY
    packedSymbols=FIELD(22);
#endif
    um_normalizer=POINTER(20);um_normalizerMin=FIELD(7);um_masterShift=FIELD(6);
    read_events();
    for(uint8_t i=0;i<um.count;i++)refresh(&um.voice[i]);
}
void um_tick(void) {
    um.ticks++;um.tickPhase=(um.tickPhase+1)&15;
    levelDirty=0;contextDirty=0;
    uint8_t bit=1;
    for(uint8_t i=0;i<um.count;i++,bit<<=1){
        UMVoice *v=&um.voice[i];
        uint8_t model=UM_READ(contextTable+((uint16_t)v->context<<2));
        uint8_t row=UM_READ(envelopeTable+((uint16_t)model<<4)+v->level);
        uint16_t at=rowTable+(uint16_t)row*3;
        if(um_word(at+1)&((uint16_t)1<<um.tickPhase)){
            uint8_t level=UM_READ(at);if(v->level!=level)levelDirty|=bit;v->level=level;
        }
    }
    if(!--um.wait)read_events();
    bit=1;
    for(uint8_t i=0;i<um.count;i++,bit<<=1){
        UMVoice *v=&um.voice[i];
        if((contextDirty&bit) || ((levelDirty&bit) && !(UM_READ(contextTable+((uint16_t)v->context<<2)+2)&32)))refresh(v);
    }
}
#if !defined(__AVR_ATtiny88__) || !defined(UM_ENABLE_AVR_ASM) || !UM_ENABLE_AVR_ASM
uint32_t um_render(void) {
    int16_t l=0,r=0,group=0;
    for(uint8_t i=0;i<um.count;i++){
        UMVoice *v=&um.voice[i];v->phase+=v->step;
        group+=v->wave[v->phase>>12];
        uint8_t mix=v->mix;
        if(mix&128){
            int16_t value;
            if(mix&32){
                uint16_t row=(uint16_t)v->level<<4;
                value=(int8_t)UM_VALUE(um_amplitudes,row+(group>>3)+8);
                value+=((uint8_t)UM_VALUE(um_amplitudes,row+(group&7)+8))>>3;
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
