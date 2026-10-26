/* Statistics are linked only in the native precision study, never the library. */
#include <stdint.h>
#include <stdio.h>
static uint64_t total_refined;
static unsigned vectors,maximum_refined,refined_vectors;
void codec2_adaptive_record(unsigned count){total_refined+=count;++vectors;maximum_refined=maximum_refined>count?maximum_refined:count;refined_vectors+=count!=0;}
#define main codec2_analysis_comparison_main
#include "analysis_compare.c"
#undef main
int main(int argc,char **argv){
    int result=codec2_analysis_comparison_main(argc,argv);
    fprintf(stderr,"{\"vectors\":%u,\"refined_bins\":%llu,\"maximum_refined_bins\":%u,\"refined_vectors\":%u}\n",vectors,(unsigned long long)total_refined,maximum_refined,refined_vectors);return result;
}
