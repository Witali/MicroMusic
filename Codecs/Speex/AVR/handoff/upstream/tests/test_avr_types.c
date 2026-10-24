/* Real upstream include/speex/speex_types.h after applying port patch */
#include "speex/speex_types.h"
typedef char validate_i16[(sizeof(spx_int16_t)==2)?1:-1];
typedef char validate_i32[(sizeof(spx_int32_t)==4)?1:-1];
typedef char validate_u16[(sizeof(spx_uint16_t)==2)?1:-1];
typedef char validate_u32[(sizeof(spx_uint32_t)==4)?1:-1];
spx_int32_t test_types(spx_int32_t a,spx_int16_t b){return a+b;}
