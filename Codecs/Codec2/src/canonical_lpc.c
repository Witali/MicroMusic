/* Keep pinned Codec2 polynomial operations; replace only cosf deterministically.
 * Original LGPL notices and implementation remain in the included vendor file.
 */
#include "lpc_math.h"
#include <math.h>
#ifdef cosf
#undef cosf
#endif
#define cosf codec2_lpc_cosf
#define lsp_to_lpc codec2_canonical_lsp_to_lpc
#include "../vendor/codec2-1.2.0/src/lsp.c"
