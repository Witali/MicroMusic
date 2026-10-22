/* Exhaustive search of minimum-span undetectable weight-4 CRC error.
 * A polynomial degree32 with low part (hex) is supplied.
 * Hash of all pairs of syndromes up to current w; O(w^2) time and space.
 * Requires about 150 MiB.  Default cutoff 6000 bits; not a global proof if none found.
 * cc -O3 -std=c11 search_crc32_4bit_burst.c -o search_crc32_4bit_burst
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#define N 6000
#define HASH_BITS 24
#define HASH_SIZE (1u<<HASH_BITS)
#define MASK (HASH_SIZE-1)
typedef struct {uint32_t key;uint16_t i,j;} Pair;
static Pair *map;
static uint32_t s[N];
static uint32_t hash(uint32_t v){
  v^=v>>16;v*=0x7feb352d;v^=v>>15;v*=0x846ca68b;v^=v>>16;return v&MASK;
}
static void insert(uint32_t key,uint16_t i,uint16_t j){
  uint32_t h=hash(key);
  while(map[h].j)h=(h+1)&MASK;
  map[h].key=key;map[h].i=i;map[h].j=j;
}
static Pair*lookup(uint32_t key){
  uint32_t h=hash(key);
  while(map[h].j){if(map[h].key==key)return &map[h];h=(h+1)&MASK;}
  return NULL;
}
int main(int argc,char**argv){
  if(argc!=2){fprintf(stderr,"Usage: %s polynomial_lower_32bits(hex)\n",argv[0]);return 1;}
  uint32_t poly=(uint32_t)strtoul(argv[1],NULL,16);
  if(!(poly&1)) {fputs("Polynomial must have constant coefficient 1\n",stderr);return 1;}
  map=calloc(HASH_SIZE,sizeof(Pair));if(!map){perror("calloc");return 2;}
  s[0]=1;
  for(int i=1;i<N;i++) s[i]=(s[i-1]<<1)^((s[i-1]&0x80000000u)?poly:0);
  for(int w=3;w<N;w++){
    int v=w-1;
    for(int u=1;u<v;u++)insert(s[u]^s[v],(uint16_t)u,(uint16_t)v);
    Pair *p=lookup(s[0]^s[w]);
    if(p){printf("poly 0x%08X: shortest 4-bit span %d bits; exponents [0,%u,%u,%d]\n",poly,w+1,p->i,p->j,w);return 0;}
  }
  printf("poly 0x%08X: no weight-4 collision in %d-bit span.\n",poly,N);
  return 0;
}
