/* Exhaustive isolated HB1 response domain; no full decoder is linked.
 * Margin/codebook arithmetic follows pinned Xiph Speex 1.2.1 sb_celp.c.
 * Original project proof driver; vendor/speex-1.2.1/COPYING retains BSD terms. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
extern const signed char high_lsp_cdbk[512],high_lsp_cdbk2[512];
extern void speex_wb_lsp8(const int16_t *,int16_t *);
#ifdef CHECK_REFERENCE
extern void original_lsp_to_lpc(const int16_t *,int16_t *,int,char *);
static uint64_t reference_cases;
#endif
static int16_t endpoints[4096][8];
typedef struct {int32_t min,max; uint64_t count,nonpositive,above32767,above65535;int lo,ln,hi,hn;int16_t low_f[8],low_a[8],high_f[8],high_a[8];} Stats;
static Stats stats[3];
static int32_t term_min[4],term_max[4],prefix_min[4],prefix_max[4];
static uint64_t prefix_outside_signed16[4];
static uint64_t vectors_checked;
static double seconds(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return t.tv_sec+t.tv_nsec*1e-9;}
static void run(int old,int next,int quarter,int slot){
 int16_t f[8],a[8];
 for(int i=0;i<8;i++){
  int16_t x=endpoints[old][i],y=endpoints[next][i];
  if(quarter==1)f[i]=x+((y>>2)-(x>>2));
  else if(quarter==2)f[i]=(x>>1)+(y>>1);
  else f[i]=y;
 }
 if(f[0]<410)f[0]=410;
 if(f[7]>25326)f[7]=25326;
 for(int i=1;i<7;i++){
  if(f[i]<f[i-1]+410)f[i]=f[i-1]+410;
  if(f[i]>f[i+1]-410)f[i]=(f[i]>>1)+((f[i+1]-410)>>1);
 }
 speex_wb_lsp8(f,a);
#ifdef CHECK_REFERENCE
 int16_t reference[8]; char arena[4096];
 original_lsp_to_lpc(f,reference,8,arena);
 if(memcmp(a,reference,sizeof(a))){fprintf(stderr,"Reference mismatch at %d,%d quarter%d\n",old,next,quarter);exit(3);}
 ++reference_cases;
#endif
 int32_t rh=8192;
 uint16_t modular=8274;
 for(int i=0;i<8;i+=2){
  int k=i/2;int32_t term=(int32_t)a[i+1]-a[i];rh+=term;
  modular=(uint16_t)(modular+(uint16_t)a[i+1]-(uint16_t)a[i]);
  if(!vectors_checked||term<term_min[k])term_min[k]=term;
  if(!vectors_checked||term>term_max[k])term_max[k]=term;
  if(!vectors_checked||rh<prefix_min[k])prefix_min[k]=rh;
  if(!vectors_checked||rh>prefix_max[k])prefix_max[k]=rh;
  prefix_outside_signed16[k]+=rh< -32768||rh>32767;
 }
 int32_t d=rh+82;
 if(d<=0||d>32767||modular!=(uint16_t)d){fprintf(stderr,"Response bound or modulo mismatch at %d,%d quarter%d\n",old,next,quarter);exit(4);}
 ++vectors_checked;
 Stats *s=stats+slot;
 if(!s->count||d<s->min){s->min=d;s->lo=old;s->ln=next;memcpy(s->low_f,f,sizeof(f));memcpy(s->low_a,a,sizeof(a));}
 if(!s->count||d>s->max){s->max=d;s->hi=old;s->hn=next;memcpy(s->high_f,f,sizeof(f));memcpy(s->high_a,a,sizeof(a));}
 ++s->count;s->nonpositive+=d<=0;s->above32767+=d>32767;s->above65535+=d>65535;
}
static void vector(const int16_t *v){putchar('[');for(int i=0;i<8;i++)printf("%s%d",i?",":"",v[i]);putchar(']');}
int main(int argc,char **argv){
 int limit=argc>1?atoi(argv[1]):4096;int pilot=argc>2;
 if(limit<1||limit>4096)return 2;
 for(int a=0;a<64;a++)for(int b=0;b<64;b++)for(int i=0;i<8;i++){
  int16_t value=6144+2560*i+32*high_lsp_cdbk[8*a+i]+16*high_lsp_cdbk2[8*b+i];
  if(value<0||(value&15)){fprintf(stderr,"Endpoint grid contract changed\n");return 5;}
  endpoints[a*64+b][i]=value;
 }
 double start=seconds();
 for(int a=0;a<limit;a++){
  for(int b=0;b<4096;b++){run(a,b,1,0);if(pilot||b>=a)run(a,b,2,1);}
  if(!(a%256)){fprintf(stderr,"Completed old endpoint %d of %d in %.6f seconds\n",a+1,limit,seconds()-start);fflush(stderr);}
 }
 for(int b=0;b<4096;b++)run(b,b,4,2);
 printf("{\"oldEndpointLimit\":%d,\"pilot\":%s,\"elapsedSeconds\":%.9f,\"rows\":[",limit,pilot?"true":"false",seconds()-start);
 for(int k=0;k<3;k++){
  Stats *s=stats+k;
  printf("%s{\"quarter\":%d,\"count\":%llu,\"min\":%d,\"max\":%d,\"nonpositive\":%llu,\"above32767\":%llu,\"above65535\":%llu,\"minOld\":%d,\"minNext\":%d,\"maxOld\":%d,\"maxNext\":%d,\"minAngles\":",k?",":"",k==2?4:k+1,(unsigned long long)s->count,s->min,s->max,(unsigned long long)s->nonpositive,(unsigned long long)s->above32767,(unsigned long long)s->above65535,s->lo,s->ln,s->hi,s->hn);
  vector(s->low_f);printf(",\"minLpc\":");vector(s->low_a);printf(",\"maxAngles\":");vector(s->high_f);printf(",\"maxLpc\":");vector(s->high_a);putchar('}');
 }

#ifdef CHECK_REFERENCE
 printf("],\"untouchedXiphComparisons\":%llu,\"termsAndPrefixes\":[",(unsigned long long)reference_cases);
 for(int k=0;k<4;k++)printf("%s{\"termIndex\":%d,\"differenceMin\":%d,\"differenceMax\":%d,\"rhPrefixMin\":%d,\"rhPrefixMax\":%d,\"prefixOutsideSigned16\":%llu}",k?",":"",k,term_min[k],term_max[k],prefix_min[k],prefix_max[k],(unsigned long long)prefix_outside_signed16[k]);
 printf("],\"modular16ResponseExact\":true,\"zeroDenResponse\":8274}\n");
#else
 puts("]}");
#endif
 return 0;
}
