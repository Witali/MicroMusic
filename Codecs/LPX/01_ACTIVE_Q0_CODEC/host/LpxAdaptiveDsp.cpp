// Exact integer synthesis/packing shared by the native and WASM controllers.
#include "LpxAdaptive.h"
#include "LpxEncoder.h"
#include "LpxSeed.h"
#include <algorithm>
#include <string.h>

namespace lpx {
static const int16_t cosine[] = {
#include "cos_table.inc"
};
static const int16_t steps[] = {
#include "scale_table.inc"
};
int clamp(int value, int low, int high) { return std::min(high, std::max(low, value)); }
static int polyMul(int value, int c) {
    if (value >= -250000 && value <= 250000) return (value * c) >> 12;
    int high = value / 16;
    return ((high * c) >> 8) + (((value - high * 16) * c) >> 12);
}
std::vector<Coefficients> coefficientTrace(const Stream& s) {
    const int frames = (s.samples + 159) / 160, shift = s.profile == 4 ? 5 : 4;
    std::vector<Coefficients> result((s.samples + 19) / 20);
    for (int fi = 0; fi < frames; ++fi) {
        int endpoints[3][10];
        const auto& previous = s.spectra[(fi ? fi - 1 : 0) / 2];
        const auto& current = s.spectra[fi / 2];
        for (int point = 0; point < 3; ++point) {
            int t = point * 8, p[2][12] = {{4096,4096},{4096,-4096}};
            for (int j = 0; j < 10; ++j) {
                int a = (previous[j] << shift) + (1 << (shift - 1));
                int b = (current[j] << shift) + (1 << (shift - 1));
                int norm = (a * (16 - t) + b * t) >> 2, index = norm >> 4, frac = norm & 15;
                int c = -(cosine[index] + ((cosine[index+1] - cosine[index]) * frac >> 4));
                int* q = p[j & 1]; int n = 2 + j / 2 * 2;
                q[n+1] = q[n-1]; q[n] = q[n-2] + polyMul(q[n-1], c);
                for (int k = n-1; k > 1; --k) q[k] = q[k-2] + polyMul(q[k-1], c) + q[k];
                q[1] += polyMul(q[0], c);
            }
            for (int j = 0; j < 10; ++j) endpoints[point][j] = clamp((p[0][j+1] + p[1][j+1]) / 2);
        }
        for (int sub = 0; sub < 8 && fi * 8 + sub < int(result.size()); ++sub)
            for (int j = 0; j < 10; ++j) {
                int a = endpoints[sub/4][j], b = endpoints[sub/4+1][j];
                result[fi*8+sub][j] = clamp(a + (b-a) * ((sub*2+1)%8) / 8);
            }
    }
    return result;
}
Pcm advance(const Stream& s, const std::vector<Coefficients>& co, int start, int end,
            SynthesisState& state, std::vector<int>* lpc) {
    Pcm output(end-start);
    if (lpc) lpc->resize(end-start);
    for (int j = start; j < end; ++j) {
        const auto& p = s.parameters[j/160]; const auto& pulse = s.pulses[j/20];
        const auto& extra = s.extras[j/40];
        int q = clamp((p[2]*state.ring[(j-p[1])&255]+8)>>4, -32,31);
        q = clamp(q + (j%20 == pulse[0] ? pulse[1] : 0) + (j%40 == extra[0] ? extra[1] : 0),-32,31);
        state.ring[j&255] = q;
        int acc = 0; for (int k = 0; k < 10; ++k) acc += (co[j/20][k]*state.h[k])>>12;
        int value = clamp(q*steps[p[0]*8]-acc);
        for (int k = 9; k; --k) state.h[k] = state.h[k-1]; state.h[0] = value;
        if (lpc) (*lpc)[j-start] = value;
        state.dd = clamp(value+((s.pre*state.dd)>>14));
        int clipped = clamp(state.dd,-16384,16384);
        int out = clamp(clipped-((s.bright*state.cc)>>14),-16384,16384); state.cc = clipped;
        output[j-start] = clamp(out*2,-32768,32767);
    }
    return output;
}
Pcm render(const Stream& s) { auto co = coefficientTrace(s); SynthesisState state; return advance(s,co,0,s.samples,state); }
uint64_t sse(const Pcm& target, const Pcm& actual, int start) {
    uint64_t sum = 0;
    for (size_t j = 0; j < actual.size(); ++j) { int64_t d = int(target[start+j])-int(actual[j]); sum += d*d; }
    return sum;
}
Pcm pwm(const Pcm& input) {
    Pcm out(input.size());
    for (size_t j = 0; j < input.size(); ++j) {
        int q14 = (int(input[j])+1)>>1;
        out[j] = (clamp(128+((q14*130+8192)>>14),0,255)-128)*256;
    }
    return out;
}
struct Writer {
    std::vector<uint8_t> bytes; int bits = 0;
    void put(int value, int width) {
        for (int i = 0; i < width; ++i, ++bits) {
            if (!(bits&7)) bytes.push_back(0);
            bytes.back() |= ((value>>i)&1)<<(bits&7);
        }
    }
    void rice(int value,int k,int width) {
        int q = value>>k;
        if (q>=8) { put(0,8); put(value,width); }
        else { put(0,q); put(1,1); put(value&((1<<k)-1),k); }
    }
};
static int riceCost(int v,int k,int width) { return v>>k >= 8 ? 8+width : (v>>k)+1+k; }
static void spectrum(Writer& w,const Spectrum& current,const Spectrum* old,int bits) {
    if (old && current == *old) { w.put(0,1); return; }
    int gaps[10],deltas[10],gc=0,dc=old?0:100000;
    for (int j = 0; j < 10; ++j) {
        gaps[j] = current[j]-(j?current[j-1]+1:0);
        int delta = old?current[j]-(*old)[j]:0;
        deltas[j] = delta>=0?2*delta:-2*delta-1;
        gc += riceCost(gaps[j],bits==5?1:2,bits);
        if (old) dc += riceCost(deltas[j],bits==5?0:1,bits+1);
    }
    bool useDelta = dc<gc; w.put(1,1); w.put(useDelta,1);
    for (int j = 0; j < 10; ++j) w.rice(useDelta?deltas[j]:gaps[j],(bits==5?1:2)-int(useDelta),bits+int(useDelta));
}
int spectralBits(const Stream& s) {
    Writer w;
    for (size_t f = 0; f < s.spectra.size(); ++f) spectrum(w,s.spectra[f],f?&s.spectra[f-1]:nullptr,s.profile==4?5:6);
    return w.bits;
}
static int active(const Stream& s) { int n=0; for (const auto& p:s.extras) n+=p[1]!=0; return n; }
int compactBytes(const Stream& s) {
    int n=active(s),frames=s.spectra.size();
    int bits=spectralBits(s)+frames*(s.profile==4?110:166)+(n?frames*8+n*10:0);
    return 22+(bits+7)/8;
}
int extraCapacity(const Stream& s,int cap,int slots) {
    int f=s.spectra.size(); if(slots<0)slots=s.extras.size();
    return std::max(0,std::min(slots,((cap-22)*8-spectralBits(s)-f*(s.profile==4?110:166)-f*8)/10));
}
std::vector<uint8_t> packV9(const Stream& s) {
    Writer w; bool enhanced=active(s)>0;
    for (size_t f=0; f<s.spectra.size(); ++f) {
        spectrum(w,s.spectra[f],f?&s.spectra[f-1]:nullptr,s.profile==4?5:6);
        for (int half=0; half<2; ++half) {
            int base=f*320+half*160; if(base>=s.samples)break;
            const auto& p=s.parameters[f*2+half]; w.put(p[0],5);w.put(p[2]/2,3);if(p[2])w.put(p[1]-18,7);
            for(int group=0;group<4 && base+group*40<s.samples;++group) {
                const auto& a=s.pulses[base/20+group*2];const auto& b=s.pulses[base/20+group*2+1];
                if(s.profile==4) { for(const auto* pulse:{&a,&b}) { w.put((*pulse)[0]-((*pulse)[0]+2)/5,4);w.put((*pulse)[1]>0,1); } }
                else { w.put((a[0]&3)|((b[0]&3)<<2),4);w.put((a[0]>>2)+5*(b[0]>>2),5);w.put(a[1]&15,4);w.put(b[1]&15,4); }
                if(enhanced) { const auto& e=s.extras[base/40+group];w.put(e[1]!=0,1);if(e[1]) { w.put(e[0],6);w.put(e[1]&15,4); } }
            }
        }
    }
    bool wide=s.samples>64000; int header=wide?17:13;
    std::vector<uint8_t> bytes(header,0);bytes.insert(bytes.end(),w.bytes.begin(),w.bytes.end());
    auto word=[&](int at,uint32_t v) { bytes[at]=v;bytes[at+1]=v>>8; };
    auto dword=[&](int at,uint32_t v) { word(at,v);word(at+2,v>>16); };
    bytes[0]='L';bytes[1]='9';bytes[2]=s.profile|(wide?64:0)|(enhanced?128:0);word(3,s.rate);
    if(wide) { dword(5,s.samples);word(9,s.pre);word(11,s.bright);dword(13,w.bytes.size()); }
    else { word(5,s.samples);word(7,s.pre);word(9,s.bright);word(11,w.bytes.size()); }
    return bytes;
}
Stream fitSeed(const Pcm& reference,int profile,int rate,int pre,bool zeroScale,double bandwidth) {
    Stream s;s.samples=reference.size();s.profile=profile;s.rate=rate;s.pre=pre;
    // Workspace was reserved by the public entry point before any adaptive
    // allocations. Avoid moving it while callers retain views into WASM memory.
    memcpy(enc_input(),reference.data(),reference.size()*2);
    int blocks=lpxSeedBegin(s.samples,profile,rate,pre,zeroScale,bandwidth);
    if(blocks<1)return Stream{};
    for(int i=0;i<blocks;++i)if(enc_step()<0)return Stream{};
    auto view=lpxSeedView();int frames=(s.samples+319)/320;
    if(!view.valid)return Stream{};
    s.spectra.resize(frames);s.parameters.resize(frames*2);s.pulses.resize(frames*16);s.extras.assign(frames*8,Pulse{{-1,0}});
    for(int f=0;f<frames;++f)for(int k=0;k<10;++k)s.spectra[f][k]=view.spectra[f][k];
    for(int b=0;b<frames*2;++b)for(int k=0;k<3;++k)s.parameters[b][k]=view.params[b][k];
    for(int p=0;p<frames*16;++p)for(int k=0;k<2;++k)s.pulses[p][k]=view.pulses[p][k];
    return s;
}
}
