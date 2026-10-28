// Compiler-generated observer metadata; NEVER link this object into player ELF.
#include <avr/io.h>
#include <avr/pgmspace.h>
#include "player_config.h"
extern "C" const uint16_t lpx_player_hardware[] PROGMEM={
    _SFR_MEM_ADDR(OCR2B),_SFR_MEM_ADDR(SPL),_SFR_MEM_ADDR(SPH),
    _SFR_MEM_ADDR(TCCR1B),_SFR_MEM_ADDR(TIMSK1),
    _SFR_MEM_ADDR(OCR1AL),_SFR_MEM_ADDR(OCR1AH),
    _SFR_MEM_ADDR(TCCR2A),_SFR_MEM_ADDR(TCCR2B),_SFR_MEM_ADDR(DDRD),
    TIMER1_COMPA_vect_num,_BV(WGM12)|_BV(CS10),_BV(OCIE1A),
    _BV(COM2B1)|_BV(WGM21)|_BV(WGM20),_BV(CS20),_BV(DDD3),
    LPX_PLAYER_QUEUE,LPX_PLAYER_PREFILL,sizeof(LpxPlayerIndex),1999
};
