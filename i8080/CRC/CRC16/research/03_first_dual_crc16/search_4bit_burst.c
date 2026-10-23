/* Exact search for shortest-span undetected 4-bit error, assuming translation invariance.
 * Check syndrome(0)^syndrome(u)^syndrome(v)^syndrome(w)==0 with 0<u<v<w.
 * No errors smaller than the found span can pass the combined CRC.
 * Build: cc -O3 search_4bit_burst.c -o search_4bit_burst
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#define N 5200
#define HASH_BITS 24
#define HASH_SIZE (1u<<HASH_BITS)
#define MASK (HASH_SIZE-1)
typedef struct {uint32_t key;uint16_t i,j;} Pair;
static Pair *map;
static uint32_t s[N];
static uint32_t poly_prod(uint16_t a, uint16_t b){
  uint64_t x=(1u<<16)|a, y=(1u<<16)|b, res=0;
  while(y){if(y&1)res^=x; x<<=1; y>>=1;}
  return (uint32_t)res;
}
static uint32_t hash(uint32_t v){
  v^=v>>16; v*=0x7feb352d; v^=v>>15; v*=0x846ca68b; v^=v>>16;
  return v&MASK;
}
static void insert(uint32_t key,uint16_t i,uint16_t j){
  uint32_t h=hash(key);
  while(map[h].j) h=(h+1)&MASK;
  map[h].key=key;map[h].i=i;map[h].j=j;
}
static Pair *lookup(uint32_t key){
  uint32_t h=hash(key);
  while(map[h].j){if(map[h].key==key)return &map[h];h=(h+1)&MASK;}
  return NULL;
}
int main(int argc,char**argv){
  if(argc!=3){fprintf(stderr,"usage: %s poly1 poly2 (hex)\n",argv[0]);return 1;}
  unsigned a,b; sscanf(argv[1],"%x",&a);sscanf(argv[2],"%x",&b);
  uint32_t poly=poly_prod(a,b);
  map=calloc(HASH_SIZE,sizeof(Pair)); if(!map){perror("calloc");return 1;}
  s[0]=1;
  for(int i=1;i<N;i++) s[i]=(s[i-1]<<1)^((s[i-1]&0x80000000u)?poly:0);
  for(int w=3;w<N;w++){
    int v=w-1;
    for(int u=1;u<v;u++)insert(s[u]^s[v],(uint16_t)u,(uint16_t)v);
    Pair *p=lookup(s[0]^s[w]);
    if(p){
      printf("poly %04X + %04X => CRC32 0x%08X; shortest 4-bit error span=%d bits; exponents [0,%u,%u,%d]\n",a,b,poly,w+1,p->i,p->j,w);
      return 0;
    }
  }
  printf("No weight-4 undetected burst found in %d bit window\n",N);
  return 0;
}
