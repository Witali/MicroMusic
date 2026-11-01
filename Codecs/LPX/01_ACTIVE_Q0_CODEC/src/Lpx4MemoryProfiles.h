#pragma once

// This changes object layout: select the same profile in every translation unit.
#define LPX4_MEMORY_PROFILE_STANDARD 0
#define LPX4_MEMORY_PROFILE_SRAM512 1
#ifndef LPX4_MEMORY_PROFILE
#define LPX4_MEMORY_PROFILE LPX4_MEMORY_PROFILE_STANDARD
#endif
#if LPX4_MEMORY_PROFILE != LPX4_MEMORY_PROFILE_STANDARD && \
    LPX4_MEMORY_PROFILE != LPX4_MEMORY_PROFILE_SRAM512
#error Unsupported LPX4_MEMORY_PROFILE
#endif
