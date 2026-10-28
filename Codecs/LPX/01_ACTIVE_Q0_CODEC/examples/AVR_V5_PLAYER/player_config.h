#pragma once
#include <stdint.h>
#ifndef LPX_PLAYER_QUEUE
#define LPX_PLAYER_QUEUE 512
#endif
#ifndef LPX_PLAYER_PREFILL
#define LPX_PLAYER_PREFILL 384
#endif
#ifndef LPX_PLAYER_IRQ_LOAD
#define LPX_PLAYER_IRQ_LOAD 0
#endif
#if LPX_PLAYER_QUEUE!=128 && LPX_PLAYER_QUEUE!=256 && LPX_PLAYER_QUEUE!=512
#error Player queue must be128,256 or512
#endif
#if LPX_PLAYER_PREFILL<1 || LPX_PLAYER_PREFILL>=LPX_PLAYER_QUEUE
#error Player prefill must be below queue size
#endif
#if LPX_PLAYER_IRQ_LOAD<0 || LPX_PLAYER_IRQ_LOAD>600
#error Player IRQ load must be0..600
#endif
#if LPX_PLAYER_QUEUE<=256
typedef uint8_t LpxPlayerIndex;
#else
typedef uint16_t LpxPlayerIndex;
#endif
