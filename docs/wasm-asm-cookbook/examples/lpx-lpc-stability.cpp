// Original standalone seam for the portable Q12 Schur guard. The companion
// Python runner compiles this with explicit compiler/sysroot paths and checks
// only generated synthetic vectors, never recordings or media fingerprints.
#include "../../../Codecs/LPX/01_ACTIVE_Q0_CODEC/host/LpxLpcStability.h"

static int16_t coefficients[10];
extern "C" int16_t* stability_input() { return coefficients; }
extern "C" int stability_test() { return lpxStableLpc(coefficients)?1:0; }
