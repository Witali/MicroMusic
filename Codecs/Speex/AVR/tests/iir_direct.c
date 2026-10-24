/* Stress the coefficient transitions, saturation and modulo-32 arithmetic. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "arch.h"
#include "iir_direct.c.inc"

static uint32_t seed=0x8b271e4d;
static uint32_t next(void) { seed^=seed<<13; seed^=seed>>17; seed^=seed<<5; return seed; }
int main(void)
{
   int32_t transposed[10]={0}, direct[15]={0};
   int16_t coef[10], input[40], output[40], original[40];
   unsigned block;
   int in_place;
   for (in_place=0;in_place<2;in_place++) {
   memset(transposed,0,sizeof(transposed));memset(direct,0,sizeof(direct));
   seed=0x8b271e4d;
   for (block=0;block<25000;block++)
   {
      int i,j;
      for (i=0;i<10;i++)
         coef[i]=block%3 ? (int16_t)next() : (int16_t)(next()%1001)-500;
      for (i=0;i<40;i++) input[i]=(int16_t)next();
      memcpy(original,input,sizeof(input));
      iir_mem16(input,coef,in_place?input:output,40,10,direct,0);
      if (!in_place) assert(!memcmp(input,original,sizeof(input)));
      for (i=0;i<40;i++)
      {
         int32_t sum=(int32_t)((uint32_t)transposed[0]+4096);
         int32_t y=(int32_t)original[i]+(sum>>13);
         int16_t neg;
         if (y>32767) y=32767;
         if (y< -32767) y= -32767;
         assert((in_place?input:output)[i]==y);
         neg= -y;
         for (j=0;j<9;j++)
            transposed[j]=(int32_t)((uint32_t)transposed[j+1]+(uint32_t)((int32_t)coef[j]*neg));
         transposed[9]=(int32_t)coef[9]*neg;
      }
   }
   }
   puts("PASS: 2000000 direct/transposed LPC samples, in-place/separate, changing coefficients and saturation");
}
