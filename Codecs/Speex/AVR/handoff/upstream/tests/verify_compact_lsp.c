/* Compare the original fixed-point Xiph lsp_to_lpc polynomial recurrence
 * with the in-place recurrence used in SPEEX_AVR_COMPACT_LSP.
 * Both receive the SAME 10 ANGLE2X() Q14 factors, so this tests only
 * polynomial reorganisation (not the Speex spx_cos implementation).
 * Test both valid-angle-like and adversarial coefficients, wrap-32 arithmetic.
 */
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <math.h>
#include <inttypes.h>
#include <time.h>
#include <limits.h>
#define MUL1632Q14(a,b) ((int32_t)((int32_t)(a)*((int32_t)(b)>>14)) + (((int32_t)(a)*((int32_t)(b)&16383))>>14))
static inline int32_t add(int32_t a,int32_t b) {return (int32_t)((uint32_t)a+(uint32_t)b);}
static inline int32_t sub(int32_t a,int32_t b) {return (int32_t)((uint32_t)a-(uint32_t)b);}
static inline int32_t round_shift(int32_t x,unsigned shift) {return (int32_t)((int32_t)((uint32_t)x+(1u<<(shift-1))) >> shift);}
static inline int16_t clamp(int32_t x) {if(x<-32767)return -32767;if(x>32767)return 32767;return (int16_t)x;}
static void ref(const int16_t f[10],int16_t out[10]) {
  int32_t p[6][13]={{0}},q[6][13]={{0}};
  const int32_t xin=1048576;
  for(int i=0;i<=5;i++) {p[i][1]=q[i][1]=0;p[i][2]=q[i][2]=xin;p[i][2+2*i]=q[i][2+2*i]=xin;}
  p[1][3]=-MUL1632Q14(f[0],p[0][2]);
  q[1][3]=-MUL1632Q14(f[1],q[0][2]);
  for(int i=1;i<5;i++) {
    int j;
    for(j=1;j<2*(i+1)-1;j++) {
      p[i+1][j+2]=add(sub(p[i][j+2],MUL1632Q14(f[2*i],p[i][j+1])),p[i][j]);
      q[i+1][j+2]=add(sub(q[i][j+2],MUL1632Q14(f[2*i+1],q[i][j+1])),q[i][j]);
    }
    p[i+1][j+2]=sub(p[i][j],MUL1632Q14(f[2*i],p[i][j+1]));
    q[i+1][j+2]=sub(q[i][j],MUL1632Q14(f[2*i+1],q[i][j+1]));
  }
  int32_t lastp=0,lastq=0;
  for(int j=1;j<=10;j++) {
    int32_t sum=sub(add(add(p[5][j+2],lastp),q[5][j+2]),lastq);
    out[j-1]=clamp(round_shift(sum,8));
    lastp=p[5][j+2];lastq=q[5][j+2];
  }
}
static void compact(const int16_t f[10],int16_t out[10]) {
  int32_t p[11]={1048576},q[11]={1048576};
  int32_t lastp=0,lastq=0;
  for(int stage=0;stage<5;stage++) {
    int degree=2*stage;
    p[degree+2]=p[degree];q[degree+2]=q[degree];
    for(int j=degree+1;j>=1;j--) {
      int32_t ap=j<=degree?p[j]:0,aq=j<=degree?q[j]:0;
      int32_t pp=j>=2?p[j-2]:0,qq=j>=2?q[j-2]:0;
      p[j]=add(sub(ap,MUL1632Q14(f[2*stage],p[j-1])),pp);
      q[j]=add(sub(aq,MUL1632Q14(f[2*stage+1],q[j-1])),qq);
    }
  }
  for(int j=1;j<=10;j++) {
    int32_t sum=sub(add(add(p[j],lastp),q[j]),lastq);
    out[j-1]=clamp(round_shift(sum,8));
    lastp=p[j];lastq=q[j];
  }
}
static uint32_t rng=0x9e3779b9;
static uint32_t xorshift(void){rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return rng;}
static int run(unsigned count,int weird) {
 for(unsigned t=0;t<count;t++){
  int16_t f[10],a[10],b[10];
  if(weird){
    for(int i=0;i<10;i++)f[i]=(int16_t)xorshift();
  }else{
    unsigned angles[10];
    for(int i=0;i<10;i++) angles[i]= 20+xorshift()%25680;
    for(int i=1;i<10;i++){unsigned z=angles[i];int j=i-1;while(j>=0&&angles[j]>z){angles[j+1]=angles[j];j--;}angles[j+1]=z;}
    for(int i=0;i<10;i++){
      double c=cos(3.14159265358979323846*(double)angles[i]/25736.0);
      int v=(int)lround(32768.0*c);
      if(v>32767)v=32767;
      if(v<-32768)v=-32768;
      f[i]=(int16_t)v;
    }
  }
  ref(f,a);compact(f,b);
  for(int i=0;i<10;i++) if(a[i]!=b[i]) {
    fprintf(stderr,"Mismatch at case %u, type %d, coefficient %d: %d!=%d\n",t,weird,i,a[i],b[i]);
    for(int j=0;j<10;j++)fprintf(stderr,"  f[%d]=%d\n",j,f[j]);
    return 1;
  }
 }
 printf("PASS: %u samples type=%s, identical 10x int16 LPC coefficients\n",count,weird?"adversarial":"ordered-angle");
 return 0;
}
int main(void){
  if(run(120000,0)||run(120000,1))return 1;
  puts("Original Xiph polynomial recurrence == memory-compact recurrence");
  return 0;
}
