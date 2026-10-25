/* Codec2 3200 64-bit frame parameter extraction.
 * Experimental decoder front-end: not complete waveform reconstruction.
 * Natural frame byte order, packed MSB-first Gray fields as in upstream pack.c.
 * Frequences represented in 25-Hz integer units (LSP differences scalar cb).
 * Copyright notice: downstream research, upstream codec2 is LGPL 2.1.
 */
#include <stdint.h>
#include <stddef.h>

typedef struct {
    uint8_t voiced[2];
    uint8_t pitch_index;
    uint8_t energy_index;
    uint8_t lspd_index[10];
    uint16_t lsp_25hz[10];
} Codec2Param3200;

static uint8_t gray_field(const uint8_t frame[8], uint8_t *bit, uint8_t width) {
    uint8_t raw = 0;
    for (uint8_t j=0; j<width; j++) {
        uint8_t at = *bit;
        raw = (uint8_t)((raw << 1) | ((frame[at>>3]>>(7-(at&7)))&1));
        (*bit)++;
    }
    raw ^= (uint8_t)(raw>>1);
    raw ^= (uint8_t)(raw>>2);
    raw ^= (uint8_t)(raw>>4);
    return raw;
}

void codec2_params_3200(const uint8_t frame[8], Codec2Param3200 *out) {
    uint8_t bit=0;
    out->voiced[0]=gray_field(frame,&bit,1);
    out->voiced[1]=gray_field(frame,&bit,1);
    out->pitch_index=gray_field(frame,&bit,7);
    out->energy_index=gray_field(frame,&bit,5);
    uint16_t cumulative=0;
    for(uint8_t i=0;i<10;i++) {
        uint8_t idx=gray_field(frame,&bit,5);
        out->lspd_index[i]=idx;
        uint8_t delta=(i>=3&&i<=5&&idx>=8)?(uint8_t)(2*idx-6):(uint8_t)(idx+1);
        cumulative=(uint16_t)(cumulative+delta);
        out->lsp_25hz[i]=cumulative;
    }
}
