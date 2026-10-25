#ifndef MICROMUSIC_AUDIO_BUFFER_H
#define MICROMUSIC_AUDIO_BUFFER_H
/* Legacy macro name: this is the ring's BYTE capacity. A mono frame occupies
   one byte; a stereo frame occupies left/right bytes. Producer emits four
   frames, and uint8_t cursors always count bytes. Thus 192 bytes retain 192
   mono frames or 96 stereo frames without increasing SRAM use. */
#if defined(UM_REQUESTED_BUFFER_FRAMES)
#if defined(UM_PWM_BUFFER_FRAMES) && UM_PWM_BUFFER_FRAMES != UM_REQUESTED_BUFFER_FRAMES
#error "UM_PWM_BUFFER_FRAMES disagrees with --buffer-frames"
#endif
#ifndef UM_PWM_BUFFER_FRAMES
#define UM_PWM_BUFFER_FRAMES UM_REQUESTED_BUFFER_FRAMES
#endif
#endif
#ifndef UM_PWM_BUFFER_FRAMES
#define UM_PWM_BUFFER_FRAMES 192
#endif
#if UM_PWM_BUFFER_FRAMES < 8 || UM_PWM_BUFFER_FRAMES > 192 || UM_PWM_BUFFER_FRAMES % 4
#error "ATtiny88 PWM buffer must contain 8..192 bytes, in multiples of four"
#endif
#endif
