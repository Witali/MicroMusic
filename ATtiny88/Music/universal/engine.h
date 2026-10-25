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
void um_init(void);
void um_tick(void);
/* Signed mixes: low 16 bits = L, high 16 bits = R. Platform outputs PWM. */
uint32_t um_render(void);
uint8_t um_output(int16_t value);
#endif
