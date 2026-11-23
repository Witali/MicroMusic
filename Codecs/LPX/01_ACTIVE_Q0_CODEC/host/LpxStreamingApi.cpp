#include "LpxStreaming.h"
#include <limits>

namespace {
std::unique_ptr<lpx::StreamingEncoder> session;
lpx::Pcm transfer;
lpx::StreamingChunk chunk;
std::vector<uint8_t> headers[2];
bool validKind(int kind) { return kind==0 || kind==1; }
}
extern "C" {
int enc_stream_create(int samples,int profile,int rate,int allowance,int calls,int normalize,int target,int maximum) {
    if(samples<1 || (normalize!=0 && normalize!=1) || target<-30 || target>-9 || maximum<0 || maximum>24)return -1;
    session.reset(new lpx::StreamingEncoder(samples,profile,rate,allowance,calls,normalize!=0));
    if(session->status())return session->status();
    transfer.resize(lpx::kLpxStreamWindow+48);chunk=lpx::StreamingChunk{};headers[0].clear();headers[1].clear();return 1;
}
int16_t* enc_stream_input() { return transfer.data(); }
int enc_stream_window() { return lpx::kLpxStreamWindow; }
int enc_stream_measure(int samples) {
    if(!session || samples<1 || samples>lpx::kLpxStreamWindow)return -1;
    return session->measure(lpx::Pcm(transfer.begin(),transfer.begin()+samples));
}
int enc_stream_plan(int target,int maximum) { return session?session->plan(target,maximum):-1; }
int enc_stream_process(int samples,int ahead) {
    if(!session || samples<1 || samples>lpx::kLpxStreamWindow || ahead<0 || ahead>48)return -1;
    return session->process(lpx::Pcm(transfer.begin(),transfer.begin()+samples),lpx::Pcm(transfer.begin()+samples,transfer.begin()+samples+ahead),chunk);
}
int enc_stream_finish() {
    if(!session)return -1;int result=session->finish(chunk);
    if(result>=0) { headers[0]=session->getHeader(false);headers[1]=session->getHeader(true); }
    return result;
}
uint8_t* enc_stream_bytes(int kind) { return validKind(kind)?(kind?chunk.candidateBytes:chunk.controlBytes).data():nullptr; }
int enc_stream_size(int kind) { return validKind(kind)?(kind?chunk.candidateBytes:chunk.controlBytes).size():-1; }
int16_t* enc_stream_pcm(int kind) { return validKind(kind)?(kind?chunk.candidatePcm:chunk.controlPcm).data():nullptr; }
int enc_stream_pcm_size(int kind) { return validKind(kind)?(kind?chunk.candidatePcm:chunk.controlPcm).size():-1; }
uint8_t* enc_stream_header(int kind) { return validKind(kind)?headers[kind].data():nullptr; }
int enc_stream_header_size(int kind) { return validKind(kind)?headers[kind].size():-1; }
int enc_stream_candidate() { return session && session->hasCandidate(); }
int enc_stream_processed() { return session?session->processed():0; }
int enc_stream_verify_put(int kind,int offset,int samples) {
    return session && samples>0 && samples<=lpx::kLpxStreamWindow?session->verifyPut(kind,offset,transfer.data(),samples):-1;
}
int enc_stream_admit() { return session?session->admit():-1; }
double enc_stream_loudness(int field) {
    if(!session)return std::numeric_limits<double>::quiet_NaN();
    const auto report=session->loudness();
    switch(field) { case 0:return report.status;case 1:return report.limited;case 2:return report.gainLimited;
        case 3:return report.input;case 4:return report.prepared;case 5:return report.decoded;case 6:return report.gainDb;
        default:return std::numeric_limits<double>::quiet_NaN(); }
}
}
