// Deterministic synthetic fixture4/320, exact compact repack; no recorded audio.
#pragma once
#include <stdint.h>
#include <avr/pgmspace.h>
static const uint8_t lpx_voice_0[] PROGMEM __attribute__((used))={
76,52,72,89,5,4,64,31,64,1,0,0,102,54,0,0,64,1,160,0,17,0,233,255,
127,10,0,12,114,208,98,79,13,4,39,189,120,243,15,
};
static const uint8_t* const lpx_voices[] PROGMEM={lpx_voice_0};
static const uint16_t lpx_sizes[] PROGMEM={39};
#define LPX_PLAYER_SEGMENTS 1
