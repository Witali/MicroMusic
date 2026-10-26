/* Explicit portable-C specialization; share all non-IFFT stages and contracts
 * with the frozen compact float implementation rather than copying its body.
 * Original Codec2 LGPL-2.1 notices remain in compact_decoder.c and vendor/.
 */
#include "codec2_hybrid.h"
#include "fixed_inverse.h"
#define codec2_compact_init codec2_hybrid_init
#define codec2_compact_decode codec2_hybrid_decode
#define compact_inverse codec2_fixed_inverse
#include "compact_decoder.c"
