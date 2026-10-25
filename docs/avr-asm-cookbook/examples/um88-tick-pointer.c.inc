/* Experimental replacement for um_tick in the existing engine.c translation
   unit: same ABI/state/ordering, loop pointers and one transition mask per tick.
   C11, AVR GCC 7.3 -Os, storage.h Flash adapter. No assembly or hardware I/O. */
void um_tick(void) {
    um.ticks++;um.tickPhase=(um.tickPhase+1)&15;
    levelDirty=0;contextDirty=0;
    uint8_t bit=1;
    const uint16_t mask=(uint16_t)1<<um.tickPhase;
    UMVoice *v=um.voice;
    for(uint8_t remaining=um.count;remaining;remaining--,v++,bit<<=1){
        uint8_t model=UM_READ(contextTable+((uint16_t)v->context<<2));
        uint8_t row=UM_READ(envelopeTable+((uint16_t)model<<4)+v->level);
        uint16_t at=rowTable+(uint16_t)row*3;
        if(um_word(at+1)&mask){
            uint8_t level=UM_READ(at);if(v->level!=level)levelDirty|=bit;v->level=level;
        }
    }
    if(!--um.wait)read_events();
    bit=1;v=um.voice;
    for(uint8_t remaining=um.count;remaining;remaining--,v++,bit<<=1){
        if((contextDirty&bit) || ((levelDirty&bit) && !(UM_READ(contextTable+((uint16_t)v->context<<2)+2)&32)))refresh(v);
    }
}
