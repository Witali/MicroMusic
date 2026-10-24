/* Mode-3 parameters from Xiph Speex 1.2.1 modes.c (BSD, see vendor COPYING).
 * Scalars/descriptors stay in SRAM; the large codebooks are read from Flash. */
#include "ltp.h"
#include "cb_search.h"
#include "quant_lsp.h"
extern const signed char gain_cdbk_lbr[];
extern const signed char exc_10_32_table[];
static const ltp_params avr_ltp = {gain_cdbk_lbr, 5, 7};
static const split_cb_params avr_innovation = {10, 4, exc_10_32_table, 5, 0};
static const SpeexSubmode speex_avr_submode = {
    -1, 0, 1, 0,
    NULL, lsp_unquant_lbr,
    NULL, pitch_unquant_3tap, &avr_ltp,
    NULL, split_cb_shape_sign_unquant, &avr_innovation,
    QCONST16(.55, 15), 160
};
