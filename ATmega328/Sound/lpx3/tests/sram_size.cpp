#include "../src/Lpx3AvrCore.h"
extern "C" __attribute__((used)) const unsigned short coreSize = sizeof(Lpx3AvrCore);
extern "C" __attribute__((used)) const unsigned short bufferSize = 512;
extern "C" __attribute__((used)) const unsigned short estimatedGlobals = sizeof(Lpx3AvrCore) + 512 + 2*2 + 2*4 + 2; // core, audio buffer, producer/consumer and flags
