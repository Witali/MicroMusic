/* Run the same API/independent-instance contract tests on the compact state. */
#include "codec2_compact.h"
#define MICROMUSIC_CODEC2_DECODER_H
#define codec2_decoder codec2_compact
#define codec2_decoder_init codec2_compact_init
#define codec2_decoder_decode codec2_compact_decode
#include "decoder_api.c"
