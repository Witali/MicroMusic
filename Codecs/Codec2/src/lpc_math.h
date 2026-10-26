/* Deterministic integer boundary math for the remaining LPC polynomial stage. */
#ifndef MICROMUSIC_CODEC2_LPC_MATH_H
#define MICROMUSIC_CODEC2_LPC_MATH_H
#include <stdint.h>
float codec2_lpc_cosf(float angle); /* finite |angle| <8 radians */
float codec2_lpc_grid_angle(uint16_t grid); /* 25-Hz units, grid <=392 */
float codec2_lpc_initial_angle(unsigned index); /* index 0..9 */
void codec2_canonical_lsp_to_lpc(float *lsp,float *ak,int order);
#endif
