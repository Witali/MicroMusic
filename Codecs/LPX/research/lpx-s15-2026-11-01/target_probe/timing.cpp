#include <avr/io.h>
#include <stddef.h>
inline void* operator new(size_t,void* p){return p;}
#include <avr/pgmspace.h>
#include "Lpx4HybridCore.h"
const uint8_t audio[] PROGMEM={
#include "audio.inc"
};
alignas(Lpx4HybridCore) uint8_t decoder_storage[sizeof(Lpx4HybridCore)];
volatile uint8_t probe_pcm,probe_error,probe_done;
volatile uint16_t probe_samples;
extern "C" uint8_t probe_core_size[sizeof(Lpx4HybridCore)];
int main(){
 Lpx4HybridCore& decoder=*new(decoder_storage) Lpx4HybridCore;
 uint8_t sample=128;
 if(decoder.begin(audio,sizeof(audio))){
  while(decoder.next(sample)){probe_pcm=sample;++probe_samples;}
 }
 probe_error=decoder.error();probe_done=1;
 for(;;){}
}
