// Independent hardware expectations, using signed-range overflow rather than
// the C executor's bitwise overflow formula. Microchip DS40002198A / DS40002307A.
const signed=x=>x<128?x:x-256;
export function arithmeticFlags(x,y,carry,subtract,previous){
  const result=subtract?x-y-carry:x+y+carry,value=result&255;
  const signedResult=subtract?signed(x)-signed(y)-carry:signed(x)+signed(y)+carry;
  const overflow=Number(signedResult< -128||signedResult>127),negative=value>>7;
  const half=Number(subtract?(x&15)-(y&15)-carry<0:(x&15)+(y&15)+carry>15);
  return (previous&0xc0)|(half<<5)|((negative^overflow)<<4)|(overflow<<3)|(negative<<2)|
    (Number(value===0)<<1)|Number(subtract?result<0:result>255);
}
export function nzvs(value,overflow,previous){
  const negative=value>>7;
  return (previous&0xe1)|((negative^overflow)<<4)|(overflow<<3)|(negative<<2)|(Number(value===0)<<1);
}
