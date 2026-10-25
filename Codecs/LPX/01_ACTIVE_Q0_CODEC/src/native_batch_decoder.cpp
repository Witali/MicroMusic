/* MicroMusic: host-only LPC batch decoding entry point.
   This translation unit is NEVER included in the ATmega328P firmware.
   The decoding algorithm is the same portable Lpx4HybridCore as in firmware.
   Build: g++ -O3 -fPIC -shared -std=c++11 -Isrc
          src/Lpx4HybridCore.cpp src/native_batch_decoder.cpp -o liblpx4batch.so
*/
#include "Lpx4HybridCore.h"
#include <stdint.h>

extern "C" int lpx4_batch_decode(
  const uint8_t* concatenated,
  const uint32_t* offsets,
  const uint32_t* sizes,
  uint32_t count,
  uint8_t* pcm,
  uint32_t pcm_stride,
  uint32_t expected_samples,
  int32_t* statuses) {
  if (!concatenated || !offsets || !sizes || !pcm || !statuses ||
      count > 512 || pcm_stride < expected_samples || expected_samples > 1000000)
    return -1;
  for (uint32_t i = 0; i < count; ++i) {
    statuses[i] = 0;
    if (sizes[i] < 20 || sizes[i] > 65535) { statuses[i] = -2; continue; }
    Lpx4HybridCore core;
    if (!core.begin(concatenated + offsets[i], (uint16_t)sizes[i]) ||
        core.samples() != expected_samples) { statuses[i] = -3; continue; }
    uint32_t pos = 0;
    uint8_t s;
    while (pos < expected_samples && core.next(s)) {
      pcm[i*pcm_stride+pos] = s;
      ++pos;
    }
    if (pos != expected_samples || !core.finished()) statuses[i] = -4;
  }
  return 0;
}

// Host-only signed 16-bit output. No PWM gain / 8-bit rounding.
// This ABI uses samples (not bytes) for stride and count, and remains separate
// from lpx4_batch_decode, preserving the previous 8-bit batch API.
extern "C" int lpx4_batch_decode_s16(
  const uint8_t* concatenated,
  const uint32_t* offsets,
  const uint32_t* sizes,
  uint32_t count,
  int16_t* pcm,
  uint32_t pcm_stride,
  uint32_t expected_samples,
  int32_t* statuses) {
  if (!concatenated || !offsets || !sizes || !pcm || !statuses ||
      count > 512 || pcm_stride < expected_samples || expected_samples > 1000000)
    return -1;
  for (uint32_t i=0; i<count; ++i) {
    statuses[i]=0;
    if (sizes[i]<20 || sizes[i]>65535) {statuses[i]=-2; continue;}
    Lpx4HybridCore core;
    if(!core.begin(concatenated+offsets[i],(uint16_t)sizes[i]) ||
       core.samples()!=expected_samples){statuses[i]=-3;continue;}
    uint32_t p=0;
    int16_t s=0;
    while(p<expected_samples && core.nextS16(s)){
       pcm[i*pcm_stride+p]=s;
       ++p;
    }
    if(p!=expected_samples || !core.finished())statuses[i]=-4;
  }
  return 0;
}
