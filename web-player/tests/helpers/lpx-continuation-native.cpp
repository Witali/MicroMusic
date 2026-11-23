#include "LpxAdaptive.h"
#include "LpxPacking.h"
#include "LpxEncoder.h"
#include "Lpx4HybridCore.h"
#include <cstdio>
#include <algorithm>
#include <cstring>
int main(){
 int cases=0;
 for(int profile:{4,6})for(int rate:{8000,12000,16000})for(int n:{641,2561,20501,65537}){
  lpx::Pcm input(n);unsigned seed=97;
  for(int i=0;i<n;++i){seed=1664525*seed+1013904223;input[i]=(int(seed>>16)-32768)/4;if((i/1280)%4==2)input[i]/=500;}
  if(!enc_reserve(n+320))return 1;
  auto whole=lpx::fitSeed(input,profile,rate,13926,false);
  auto expected=lpx::render(whole);lpx::Stream joined;joined.profile=profile;joined.rate=rate;joined.samples=n;
  lpx::Stream context;context.allowExtras=false; lpx::Pcm decoded;
  lpx::V9PacketWriter writer(false);std::vector<uint8_t> payload;
  for(int at=0;at<n;at+=20480){
   int count=std::min(20480,n-at);lpx::Pcm part(input.begin()+at,input.begin()+at+count);
   context.lookahead.assign(input.begin()+at+count,input.begin()+std::min(n,at+count+48));
   if(!enc_reserve(count+320))return 2;
   auto next=lpx::fitSeed(part,profile,rate,13926,false,.97,&context);
   if(!writer.append(next))return 8;
   auto completeBytes=writer.drain();payload.insert(payload.end(),completeBytes.begin(),completeBytes.end());
   auto co=lpx::coefficientTrace(next);auto state=next.initial;auto pcm=lpx::advance(next,co,0,count,state);
   decoded.insert(decoded.end(),pcm.begin(),pcm.end());
   joined.spectra.insert(joined.spectra.end(),next.spectra.begin(),next.spectra.end());
   joined.parameters.insert(joined.parameters.end(),next.parameters.begin(),next.parameters.end());
   joined.pulses.insert(joined.pulses.end(),next.pulses.begin(),next.pulses.end());
   joined.extras.insert(joined.extras.end(),next.extras.begin(),next.extras.end());
   if(at+count<n){
    context.initial=state;context.continuation=true;context.previousSpectrum=next.spectra.back();
    std::copy(part.end()-172,part.end(),context.previousInput.begin());
    std::copy(co.end()-8,co.end(),context.previousCoefficients.begin());
   }
  }
  if(joined.spectra!=whole.spectra||joined.parameters!=whole.parameters||joined.pulses!=whole.pulses||decoded!=expected){
   std::fprintf(stderr,"mismatch p=%d rate=%d n=%d spectra=%d params=%d pulses=%d pcm=%d\n",profile,rate,n,joined.spectra==whole.spectra,joined.parameters==whole.parameters,joined.pulses==whole.pulses,decoded==expected);return 3;
  }
  auto bytes=lpx::packV9(joined);
  if(bytes!=lpx::packV9(whole))return 4;
  auto finalBytes=writer.finish();payload.insert(payload.end(),finalBytes.begin(),finalBytes.end());
  auto continuous=lpx::v9Header(n,profile,rate,13926,0,false,payload.size());
  continuous.insert(continuous.end(),payload.begin(),payload.end());if(continuous!=bytes)return 9;
  Lpx4HybridCore core;if(!core.beginWideV9(bytes.data(),bytes.size()))return 5;
  for(int x:decoded){int16_t actual;if(!core.nextS16(actual)||actual!=x)return 6;}
  int16_t tail;if(core.nextS16(tail)||core.error()||!core.finished())return 7;
  ++cases;
 }
 std::printf("{\"continuedSeedCases\":%d,\"exactContinuousBytesAndPcm\":true}\n",cases);
}
