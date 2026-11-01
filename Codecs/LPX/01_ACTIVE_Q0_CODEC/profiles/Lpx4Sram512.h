#pragma once

// Force-include this configuration for the core AND every consumer. Arithmetic
// and real processor selection remain independent; C is still the default.
#ifndef LPX4_MEMORY_PROFILE
#define LPX4_MEMORY_PROFILE 1
#endif
#include "../src/Lpx4MemoryProfiles.h"
#if LPX4_MEMORY_PROFILE != LPX4_MEMORY_PROFILE_SRAM512
#error Lpx4Sram512.h conflicts with LPX4_MEMORY_PROFILE
#endif
#ifndef LPX4_ENABLE_SPEECH
#define LPX4_ENABLE_SPEECH 1
#endif
#ifndef LPX4_ENABLE_SPEECH_COMPACT
#define LPX4_ENABLE_SPEECH_COMPACT 1
#endif
#ifndef LPX4_COMPACT_ONLY
#define LPX4_COMPACT_ONLY 1
#endif
#if !LPX4_ENABLE_SPEECH || !LPX4_ENABLE_SPEECH_COMPACT || !LPX4_COMPACT_ONLY
#error Lpx4Sram512.h requires compact v5 speech support
#endif
