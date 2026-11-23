#include "LpxCuda.h"
#include <chrono>
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <cmath>
#include <algorithm>
#include <vector>
#include <limits.h>

static int clip(int value,int low=-32767,int high=32767) { return std::min(high,std::max(low,value)); }
static double referenceTrial(const LpxCudaJob& job,const LpxCudaChoice& choice,
    LpxCudaState& state,int group,int pos,int amp) {
    double loss=0;int cursor=job.cursor+group*20;
    for(int j=0;j<20;++j) {
        int q=clip((choice.gain*state.ring[(cursor+j-choice.lag)&255]+8)>>4,-32,31);
        q=clip(q+(j==pos?amp:0),-32,31);state.ring[(cursor+j)&255]=q;
        int acc=0;for(int k=0;k<10;++k)acc+=(int(job.coefficients[group][k])*state.h[k])>>12;
        int pred=clip(q*choice.step-acc);
        for(int k=9;k;--k)state.h[k]=state.h[k-1];state.h[0]=pred;
        state.dd=clip(pred+((job.pre*state.dd)>>14));
        int sample=clip(clip(state.dd,-16384,16384)*2,-32768,32767);
        double d=sample-int(job.samples[group*20+j]);loss+=d*d;
    }
    return loss;
}
static LpxCudaResult referenceChoice(const LpxCudaJob& job,int choice) {
    LpxCudaResult result={};result.finalState=job.initial;result.choice=choice;
    for(int group=0;group<8;++group) {
        double best=HUGE_VAL;int bestPos=0,bestAmp=0;
        for(int position=0;position<(job.profile==4?16:20);++position) {
            int pos=job.profile==4?position+(position+2)/4:position;
            for(int ai=0;ai<(job.profile==4?2:16);++ai) {
                int amp=job.profile==4?(ai?8:-8):ai-8;LpxCudaState state=result.finalState;
                double loss=referenceTrial(job,job.choices[choice],state,group,pos,amp);
                if(loss<best) { best=loss;bestPos=pos;bestAmp=amp; }
            }
        }
        result.pulses[group][0]=bestPos;result.pulses[group][1]=bestAmp;
        result.loss+=referenceTrial(job,job.choices[choice],result.finalState,group,bestPos,bestAmp);
    }
    return result;
}
static LpxCudaResult reference(const LpxCudaJob& job) {
    LpxCudaResult best={};best.loss=HUGE_VAL;
    for(int i=0;i<job.count;++i) { auto out=referenceChoice(job,i);if(out.loss<best.loss)best=out; }
    return best;
}
static uint32_t seed=0x963e45a1;
static uint32_t randomBits() { seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;return seed; }
static void pattern(LpxCudaJob& job,int index) {
    for(int& value:job.initial.h)value=index==0?0:index==1?int(randomBits()%12001)-6000:index==2?32767:index==3?-32768:(randomBits()&1?32767:-32768);
    job.initial.dd=index==0?0:index==1?int(randomBits()%12001)-6000:index==2?32767:index==3?-32768:(randomBits()&1?32767:-32768);
    for(int& value:job.initial.ring)value=index==0?0:index==1?int(randomBits()%64)-32:(randomBits()&1?31:-32);
    for(auto& row:job.coefficients)for(auto& value:row)value=index==0?0:index==1?int(randomBits()%1001)-500:index==2?32767:index==3?-32768:(randomBits()&1?32767:-32768);
    for(auto& value:job.samples)value=index==0?0:index==1?int(randomBits()%24001)-12000:(randomBits()&1?32767:-32768);
}
static int checks=0,tuples=0;static double cpuMs=0,gpuMs=0;
static bool run(LpxCudaJob& job) {
    using Clock=std::chrono::steady_clock;auto start=Clock::now();auto expected=reference(job);
    cpuMs+=std::chrono::duration<double,std::milli>(Clock::now()-start).count();
    LpxCudaResult actual;start=Clock::now();
    if(!lpxCudaSearch(job,actual)) { fprintf(stderr,"CUDA error: %s\n",lpxCudaError());return false; }
    gpuMs+=std::chrono::duration<double,std::milli>(Clock::now()-start).count();
    ++checks;tuples+=job.count;
    if(actual.choice!=expected.choice || actual.loss!=expected.loss || memcmp(actual.pulses,expected.pulses,sizeof(actual.pulses))
        || memcmp(&actual.finalState,&expected.finalState,sizeof(actual.finalState))) {
        fprintf(stderr,"Mismatch check=%d P%d cursor%d pre%d count%d choice%d/%d loss%.0f/%.0f pulsesEqual%d stateEqual%d\n",checks,job.profile,job.cursor,job.pre,job.count,actual.choice,expected.choice,actual.loss,expected.loss,
            !memcmp(actual.pulses,expected.pulses,sizeof(actual.pulses)),!memcmp(&actual.finalState,&expected.finalState,sizeof(actual.finalState)));return false;
    }
    return true;
}
int main() {
    if(!lpxCudaAvailable()) { fprintf(stderr,"CUDA unavailable: %s\n",lpxCudaError());return 1; }
    const int lags[]={18,19,20,145},gains[]={0,2,14},scales[]={0,6,10,31},steps[]={0,1,4,32767},pres[]={0,8192,13926},cursors[]={0,240,260};
    LpxCudaJob job={};job.count=1;
    for(int profile:{4,6})for(int p=0;p<5;++p)for(int lag:lags)for(int gain:gains)for(int i=0;i<4;++i)for(int pre:pres)for(int cursor:cursors) {
        job.profile=profile;job.pre=pre;job.cursor=cursor;pattern(job,p);job.choices[0]={scales[i],lag,gain,steps[i]};
        if(!run(job))return 2;
    }
    for(int profile:{4,6})for(int p=0;p<5;++p)for(int count:{2,7,21,32,127,320,512}) {
        job.profile=profile;job.pre=13926;job.cursor=260;job.count=count;pattern(job,p);
        for(int i=0;i<count;++i)job.choices[i]={scales[i%4],lags[(i/4)%4],gains[(i/16)%3],steps[i%4]};
        if(!run(job))return 3;
        std::reverse(job.choices,job.choices+count);if(!run(job))return 4;
    }
    int rejected=0;
    for(int invalid=0;invalid<10;++invalid) {
        auto bad=job;LpxCudaResult ignored;
        if(invalid==0)bad.count=0;
        if(invalid==1)bad.count=kLpxCudaMaxChoices+1;
        if(invalid==2)bad.profile=15;
        if(invalid==3)bad.pre=16385;
        if(invalid==4)bad.cursor=-1;
        if(invalid==5)bad.cursor=INT_MAX;
        if(invalid==6)bad.choices[0].gain=3;
        if(invalid==7)bad.choices[0].lag=17;
        if(invalid==8)bad.initial.ring[0]=32;
        if(invalid==9)bad.initial.h[0]=INT_MIN;
        if(lpxCudaSearch(bad,ignored))return 5;++rejected;
    }
    job.count=1;job.profile=6;job.pre=13926;job.cursor=0;pattern(job,0);job.choices[0]={0,18,0,0};
    if(!run(job))return 6; // Rejected jobs must not poison persistent GPU state.
    printf("{\"checks\":%d,\"tuples\":%d,\"rejectedInvalidJobs\":%d,\"cpuReferenceMs\":%.3f,\"gpuSearchMs\":%.3f,\"exact\":true}\n",checks,tuples,rejected,cpuMs,gpuMs);
}
