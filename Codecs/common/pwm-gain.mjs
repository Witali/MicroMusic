// Independent integer reference for the producer's constant Q7 output gain.
export function pwmGain(bytes,numerator=128){
  if(!Number.isInteger(numerator)||numerator<128||numerator>255)throw Error('Invalid Q7 output gain');
  return Uint8Array.from(bytes,value=>Math.max(0,Math.min(255,Math.floor((value*numerator+64)/128)+128-numerator)));
}
