#ifndef MICROMUSIC_AUDIO_CHANNELS_H
#define MICROMUSIC_AUDIO_CHANNELS_H
/* Preprocessor-only configuration, shared by C and assembler sources.
 * A platform header supplied with -include may choose UM_OUTPUT_CHANNELS.
 * The builder requests the effective score's mono/stereo output explicitly. */
#if defined(UM_REQUESTED_OUTPUT_CHANNELS)
#if UM_REQUESTED_OUTPUT_CHANNELS != 1 && UM_REQUESTED_OUTPUT_CHANNELS != 2
#error "UM_REQUESTED_OUTPUT_CHANNELS must be 1 (mono) or 2 (stereo)"
#endif
#if defined(UM_OUTPUT_CHANNELS) && UM_OUTPUT_CHANNELS != UM_REQUESTED_OUTPUT_CHANNELS
#error "UM_OUTPUT_CHANNELS disagrees with the requested build channels"
#endif
#ifndef UM_OUTPUT_CHANNELS
#define UM_OUTPUT_CHANNELS UM_REQUESTED_OUTPUT_CHANNELS
#endif
#endif
#ifndef UM_OUTPUT_CHANNELS
#define UM_OUTPUT_CHANNELS 1
#endif
#if UM_OUTPUT_CHANNELS != 1 && UM_OUTPUT_CHANNELS != 2
#error "UM_OUTPUT_CHANNELS must be 1 (mono) or 2 (stereo)"
#endif
#endif
