// Original project implementation of the existing exact LPX pulse search.
// Build explicitly with LPX_ENCODER_ENABLE_CUDA=1 and the NVIDIA CUDA compiler.
// No relaxed arithmetic or trained tables; the portable search remains in
// LpxEncoder.cpp. The GPU only evaluates independent candidates.
#if !defined(__CUDACC__) || !defined(LPX_ENCODER_ENABLE_CUDA) || LPX_ENCODER_ENABLE_CUDA != 1
#error Compile the CUDA backend with nvcc and LPX_ENCODER_ENABLE_CUDA=1
#endif
#include "../LpxCuda.h"
#include <cuda_runtime.h>
#include <math_constants.h>
#include <stddef.h>
#include <limits.h>

static_assert(sizeof(int) == 4 && sizeof(int16_t) == 2, "LPX CUDA requires 32-bit int / 16-bit PCM");
static_assert((-1 >> 1) == -1, "LPX CUDA requires arithmetic signed shifts");
static_assert(sizeof(LpxCudaState) == 1068, "State layout must match the portable encoder");

namespace {
__device__ __forceinline__ int clip(int value, int low=-32767, int high=32767) {
    return value<low?low:value>high?high:value;
}
__device__ __forceinline__ void pulse(int profile,int ordinal,int& pos,int& amp) {
    if(profile==4) { int position=ordinal/2;pos=position+(position+2)/4;amp=ordinal&1?8:-8; }
    else { pos=ordinal/16;amp=ordinal%16-8; }
}
__device__ __forceinline__ double trial(const LpxCudaState& initial,const int16_t* co,
    const int16_t* samples,int cursor,int step,int lag,int gain,int pre,int pos,int amp) {
    int h[10],dd=initial.dd,q0=0,q1=0;double loss=0;
#pragma unroll
    for(int k=0;k<10;++k)h[k]=initial.h[k];
    for(int j=0;j<20;++j) {
        // Only lag18/19 can read samples generated within this 20-sample trial.
        int delayed=j>=lag?(j-lag==0?q0:q1):initial.ring[(cursor+j-lag)&255];
        int q=clip((gain*delayed+8)>>4,-32,31);
        q=clip(q+(j==pos?amp:0),-32,31);
        if(j==0)q0=q;if(j==1)q1=q;
        int acc=0;
#pragma unroll
        for(int k=0;k<10;++k)acc+=(int(co[k])*h[k])>>12;
        int pred=clip(q*step-acc);
#pragma unroll
        for(int k=9;k>0;--k)h[k]=h[k-1];h[0]=pred;
        dd=clip(pred+((pre*dd)>>14));
        int sample=clip(clip(dd,-16384,16384)*2,-32768,32767);
        double delta=sample-int(samples[j]);loss+=delta*delta;
    }
    return loss;
}
__device__ void replay(LpxCudaState& state,const int16_t* co,int cursor,
    int step,int lag,int gain,int pre,int pos,int amp) {
    for(int j=0;j<20;++j) {
        int q=clip((gain*state.ring[(cursor+j-lag)&255]+8)>>4,-32,31);
        q=clip(q+(j==pos?amp:0),-32,31);state.ring[(cursor+j)&255]=q;
        int acc=0;
#pragma unroll
        for(int k=0;k<10;++k)acc+=(int(co[k])*state.h[k])>>12;
        int pred=clip(q*step-acc);
#pragma unroll
        for(int k=9;k>0;--k)state.h[k]=state.h[k-1];state.h[0]=pred;
        state.dd=clip(pred+((pre*state.dd)>>14));
    }
}
__device__ __forceinline__ void reduce(double* loss,int* ordinal) {
    int lane=threadIdx.x;
    for(int stride=256;stride;stride/=2) {
        if(lane<stride) {
            double other=loss[lane+stride];int index=ordinal[lane+stride];
            if(other<loss[lane] || (other==loss[lane] && index<ordinal[lane])) {
                loss[lane]=other;ordinal[lane]=index;
            }
        }
        __syncthreads();
    }
}
__global__ void searchChoices(const LpxCudaJob* job,LpxCudaResult* output) {
    __shared__ LpxCudaState current;
    __shared__ int16_t coefficients[8][10],samples[160];
    __shared__ double errors[512];
    __shared__ int ordinals[512];
    int lane=threadIdx.x,index=blockIdx.x;
    if(lane==0)current=job->initial;
    if(lane<80)reinterpret_cast<int16_t*>(coefficients)[lane]=reinterpret_cast<const int16_t*>(job->coefficients)[lane];
    if(lane<160)samples[lane]=job->samples[lane];
    __syncthreads();
    const LpxCudaChoice choice=job->choices[index];
    int candidates=job->profile==4?32:320;double total=0;
    for(int group=0;group<8;++group) {
        int pos=0,amp=0;double loss=CUDART_INF;
        if(lane<candidates) {
            pulse(job->profile,lane,pos,amp);
            loss=trial(current,coefficients[group],samples+group*20,job->cursor+group*20,
                choice.step,choice.lag,choice.gain,job->pre,pos,amp);
        }
        errors[lane]=loss;ordinals[lane]=lane<candidates?lane:INT_MAX;
        __syncthreads();reduce(errors,ordinals);
        if(lane==0) {
            pulse(job->profile,ordinals[0],pos,amp);total+=errors[0];
            output[index].pulses[group][0]=pos;output[index].pulses[group][1]=amp;
            replay(current,coefficients[group],job->cursor+group*20,
                choice.step,choice.lag,choice.gain,job->pre,pos,amp);
        }
        __syncthreads();
    }
    if(lane==0) { output[index].loss=total;output[index].choice=index;output[index].finalState=current; }
}
__global__ void selectChoice(const LpxCudaResult* choices,int count,LpxCudaResult* output) {
    __shared__ double errors[512];__shared__ int ordinals[512];int lane=threadIdx.x;
    errors[lane]=lane<count?choices[lane].loss:CUDART_INF;ordinals[lane]=lane<count?lane:INT_MAX;
    __syncthreads();reduce(errors,ordinals);
    if(lane==0)*output=choices[ordinals[0]];
}
static const char* errorMessage="CUDA has not been initialized";
struct DeviceBuffers {
    cudaStream_t stream=nullptr;
    LpxCudaJob* job=nullptr;
    LpxCudaResult* choices=nullptr;
    LpxCudaResult* winner=nullptr;
    int device=-1;
    bool ready=false;
    ~DeviceBuffers() {
        if(stream)cudaStreamSynchronize(stream);
        if(winner)cudaFree(winner);if(choices)cudaFree(choices);if(job)cudaFree(job);
        if(stream)cudaStreamDestroy(stream);
    }
};
static DeviceBuffers buffers;
static bool check(cudaError_t error) {
    if(error==cudaSuccess)return true;errorMessage=cudaGetErrorString(error);return false;
}
static bool initialize() {
    int device=0;
    if(!check(cudaGetDevice(&device)))return false;
    if(buffers.stream && device!=buffers.device) {
        errorMessage="CUDA device changed after LPX initialization";return false;
    }
    if(buffers.ready) {
        return true;
    }
    buffers.device=device;
    if(!buffers.stream && !check(cudaStreamCreateWithFlags(&buffers.stream,cudaStreamNonBlocking)))return false;
    if(!buffers.job && !check(cudaMalloc(reinterpret_cast<void**>(&buffers.job),sizeof(LpxCudaJob))))return false;
    if(!buffers.choices && !check(cudaMalloc(reinterpret_cast<void**>(&buffers.choices),sizeof(LpxCudaResult)*kLpxCudaMaxChoices)))return false;
    if(!buffers.winner && !check(cudaMalloc(reinterpret_cast<void**>(&buffers.winner),sizeof(LpxCudaResult))))return false;
    cudaFuncAttributes attributes;
    if(!check(cudaFuncGetAttributes(&attributes,searchChoices)))return false;
    buffers.device=device;buffers.ready=true;errorMessage="";return true;
}
static bool valid(const LpxCudaJob& job) {
    if((job.profile!=4 && job.profile!=6) || job.pre<0 || job.pre>16384 || job.count<1
        || job.count>kLpxCudaMaxChoices || job.cursor<0 || job.cursor>INT_MAX-160)return false;
    for(int x:job.initial.h)if(x<-32768 || x>32767)return false;
    if(job.initial.dd<-32768 || job.initial.dd>32767)return false;
    for(int x:job.initial.ring)if(x<-32 || x>31)return false;
    for(int i=0;i<job.count;++i) {
        const auto& c=job.choices[i];
        if(c.scale<0 || c.scale>31 || c.lag<18 || c.lag>145 || c.gain<0 || c.gain>14
            || (c.gain&1) || c.step<0 || c.step>32767)return false;
    }
    return true;
}
}
bool lpxCudaAvailable() { return initialize(); }
bool lpxCudaSearch(const LpxCudaJob& job,LpxCudaResult& result) {
    if(!valid(job)) { errorMessage="Invalid LPX CUDA search job";return false; }
    if(!initialize())return false;
    const size_t bytes=offsetof(LpxCudaJob,choices)+job.count*sizeof(LpxCudaChoice);
    if(!check(cudaMemcpyAsync(buffers.job,&job,bytes,cudaMemcpyHostToDevice,buffers.stream)))return false;
    searchChoices<<<job.count,512,0,buffers.stream>>>(buffers.job,buffers.choices);
    if(!check(cudaGetLastError()))return false;
    selectChoice<<<1,512,0,buffers.stream>>>(buffers.choices,job.count,buffers.winner);
    if(!check(cudaGetLastError()))return false;
    if(!check(cudaMemcpyAsync(&result,buffers.winner,sizeof(result),cudaMemcpyDeviceToHost,buffers.stream)))return false;
    if(!check(cudaStreamSynchronize(buffers.stream)))return false;
    errorMessage="";return true;
}
const char* lpxCudaError() { return errorMessage; }
