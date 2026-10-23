#include <cstdio>
#include <cstdint>
#include <vector>
#include <cstring>
#include <cstdlib>
#include <algorithm>
#include <chrono>
using namespace std;
static inline uint32_t hash32(uint32_t x){x^=x>>16;x*=0x7feb352dU;x^=x>>15;x*=0x846ca68bU;x^=x>>16;return x;}
static uint32_t mult(uint32_t a,uint32_t b){uint64_t r=0,x=a;while(b){if(b&1)r^=x;x<<=1;b>>=1;}return (uint32_t)r;}
static uint32_t mod(uint32_t a,uint32_t b){while(a && 31-__builtin_clz(a)>=31-__builtin_clz(b))a^=b<<(31-__builtin_clz(a)-(31-__builtin_clz(b)));return a;}
static uint32_t gcdpoly(uint32_t a,uint32_t b){while(b){uint32_t t=mod(a,b);a=b;b=t;}return a;}
static int period(uint16_t p){uint32_t x=1;for(int k=1;k<=65535;k++){x=((x<<1)^((x&0x8000)?p:0))&0xffff;if(x==1)return k;}return -1;}
static int lcm(int a,int b){int x=a,y=b;while(y){int z=x%y;x=y;y=z;}return (int)((int64_t)a*b/x);}
struct Result {int span;int i;int j;int m;};
static Result min4(uint32_t Q,int LIMIT) {
 constexpr uint32_t SIZE=1u<<25;
 static vector<uint32_t> keys(SIZE);
 memset(keys.data(),0,SIZE*sizeof(uint32_t));
 vector<uint32_t> s(LIMIT+1);
 s[0]=1;
 for(int k=1;k<=LIMIT;k++)s[k]=(s[k-1]<<1)^((s[k-1]&0x80000000)?Q:0);
 for(int m=3;m<LIMIT;m++){
   uint32_t target=s[0]^s[m];
   uint32_t h=hash32(target)&(SIZE-1);
   while(keys[h] && keys[h]!=target)h=(h+1)&(SIZE-1);
   if(keys[h]==target){
     for(int j=2;j<m;j++)for(int i=1;i<j;i++)if((s[i]^s[j])==target)
       return {m+1,i,j,m};
     fprintf(stderr,"bad witness!\n");exit(7);
   }
   for(int i=1;i<m;i++){
     uint32_t k=s[i]^s[m];
     if(!k){fprintf(stderr,"Double error in small span!\n");return {-1,-1,-1,-1};}
     uint32_t pos=hash32(k)&(SIZE-1);
     while(keys[pos] && keys[pos]!=k)pos=(pos+1)&(SIZE-1);
     keys[pos]=k;
   }
 }
 return {0,0,0,0};
}
int main(int argc,char**argv){int LIMIT=argc>1?atoi(argv[1]):6200;int weightmax=argc>2?atoi(argv[2]):3;
 printf("p1,p2,wt2,period1,period2,lcm,gcd,composite,span4,i,j,m,seconds\n");fflush(stdout);
 for(int p=1;p<=511;p+=2){
   if(__builtin_popcount((unsigned)p)>weightmax || p==7)continue;
   int t1=32767,t2=period(p),t=lcm(t1,t2);
   uint32_t g=gcdpoly(0x10007,0x10000|p);
   if(g!=1 || t<=524287)continue;
   uint32_t Q=mult(0x10007,0x10000|p);
   auto t0=chrono::steady_clock::now();
   Result r=min4(Q,LIMIT);
   double secs=chrono::duration<double>(chrono::steady_clock::now()-t0).count();
   printf("0007,%04X,%d,%d,%d,%d,%X,%08X,%d,%d,%d,%d,%.3f\n",p,__builtin_popcount((unsigned)p),t1,t2,t,g,Q,r.span,r.i,r.j,r.m,secs);fflush(stdout);
 }
}
