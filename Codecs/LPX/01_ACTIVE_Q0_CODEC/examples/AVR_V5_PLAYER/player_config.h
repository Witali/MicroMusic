#pragma once
#include <stdint.h>
#ifndef LPX_PLAYER_QUEUE
#define LPX_PLAYER_QUEUE 256
#endif
#ifndef LPX_PLAYER_PREFILL
#define LPX_PLAYER_PREFILL (LPX_PLAYER_QUEUE*3/4)
#endif
#ifndef LPX_PLAYER_IRQ_LOAD
#define LPX_PLAYER_IRQ_LOAD 0
#endif
#if LPX_PLAYER_QUEUE!=128 && LPX_PLAYER_QUEUE!=256 && LPX_PLAYER_QUEUE!=512
#error Player queue must be 128, 256 or 512
#endif
#if LPX_PLAYER_PREFILL<1 || LPX_PLAYER_PREFILL>=LPX_PLAYER_QUEUE
#error Player prefill must be below queue size
#endif
#if LPX_PLAYER_IRQ_LOAD<0 || LPX_PLAYER_IRQ_LOAD>600
#error Player IRQ load must be 0..600
#endif
#if LPX_PLAYER_QUEUE<=256
typedef uint8_t LpxPlayerIndex;
#else
typedef uint16_t LpxPlayerIndex;
#endif
