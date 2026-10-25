#ifndef MICROMUSIC_AUDIO_BUFFER_H
#define MICROMUSIC_AUDIO_BUFFER_H
/* One byte per mono PWM frame. Cursor is uint8_t; producer emits four frames. */
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
#error "ATtiny88 PWM buffer must contain 8..192 frames, in multiples of four"
#endif
#endif
