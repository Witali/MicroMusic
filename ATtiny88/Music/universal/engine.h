#ifndef MICROMUSIC_UNIVERSAL_H
#define MICROMUSIC_UNIVERSAL_H
#include <stdint.h>
#define UM_VOICES 8
#ifndef UM_SONG_ADDRESS
#define UM_SONG_ADDRESS 2560
#endif
/* No device registers or CPU-specific arithmetic in this interface. */
typedef struct {
    uint16_t phase, step;
    int8_t wave[16];
    uint8_t level, context, mix;
} UMVoice;
typedef struct {
    UMVoice voice[UM_VOICES];
    uint16_t stream, pending[13], ticks;
    uint8_t depth, wait, count, tickPhase, drumMode, drumPhase, noiseHigh;
} UMState;
extern UMState um;
extern uint16_t um_normalizer;
extern int8_t um_normalizerMin;
extern uint8_t um_masterShift;
extern uint8_t um_channels;
void um_init(void);
void um_tick(void);
/* Two signed 16-bit mixes, left in low word and right in high word. Mono
   compositions use identical pans; channel selection belongs to the platform. */
uint32_t um_render(void);
/* Flash access goes through storage.h in C; optional AVR arithmetic/cache backend. */
void um_scale_wave(uint16_t source,int8_t *target,uint8_t level,uint8_t gain);
uint8_t um_output(int16_t value);
#endif
