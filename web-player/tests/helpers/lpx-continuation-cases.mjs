// Independent synthetic source; no recorded media or fitted source parameters.
const fractions=Object.freeze([.283,.375,.417,.435]);

export function toneBurstTrain(rate=16000,samples=20528) {
  const reference=Int16Array.from({length:samples},(_,i)=>{
    const at=i%640,frequency=fractions[Math.floor(i/640)%fractions.length];
    const attack=Math.min(1,at/12),decay=Math.exp(-at/rate/.025);
    return Math.round(9000*attack*decay*Math.sin(2*Math.PI*frequency*i));
  });
  return {rate,reference,partials:fractions.map(frequency=>({frequency:frequency*rate}))};
}
