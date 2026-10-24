#!/usr/bin/env python3
"""Download four real spoken voice recordings (Wikimedia Commons) and create Speex test streams.
Copyright and attribution metadata are in REAL_SPEECH_SOURCES.md. Audio is not bundled here.
Needs Python 3, ffmpeg with libspeex encoder/decoder, and network access.
"""
from pathlib import Path
from urllib.request import Request, urlopen
import shutil, subprocess, sys, argparse

SOURCE_ITEMS = [
    ('ru_male', 'https://upload.wikimedia.org/wikipedia/commons/c/c3/Ru-%D0%9B_%D0%9F%D1%83%D1%88%D0%BA%D0%B8%D0%BD%D1%83.ogg'),
    ('ru_female', 'https://upload.wikimedia.org/wikipedia/commons/9/9f/Ru-Black-square-_intro.ogg'),
    ('en_male', 'https://upload.wikimedia.org/wikipedia/commons/b/bd/Use_common_sense.ogg'),
    ('en_female', 'https://upload.wikimedia.org/wikipedia/commons/7/73/Portrait_of_a_lady_1_voice.ogg'),
]

def cmd(*parts):
    print('+', ' '.join(map(str,parts)),flush=True)
    subprocess.run(list(map(str,parts)),check=True)

def download(url,dest):
    req=Request(url,headers={'User-Agent':'Speex AVR audio codec evaluation (Wikimedia Commons, attribution included in REAL_SPEECH_SOURCES.md)'})
    with urlopen(req,timeout=90) as input_stream,dest.open('wb') as output_stream:
        shutil.copyfileobj(input_stream,output_stream)
    if dest.stat().st_size<1024: raise RuntimeError('Unexpectedly small file: '+str(dest))

def ogg_packets(src):
    import struct
    pos=0; pending=bytearray(); serial=None
    while pos<len(src):
        if pos+27>len(src) or src[pos:pos+4]!=b'OggS' or src[pos+4]!=0:raise ValueError('Not a complete Ogg file')
        nseg=src[pos+26];lacing=src[pos+27:pos+27+nseg];q=pos+27+nseg
        cur_serial=struct.unpack_from('<I',src,pos+14)[0]
        if serial is None:serial=cur_serial
        if cur_serial!=serial: raise ValueError('Chained Ogg is not supported')
        if len(lacing)!=nseg:raise ValueError('Invalid lacing')
        for n in lacing:
            if q+n>len(src):raise ValueError('Truncated Ogg data')
            pending.extend(src[q:q+n]);q+=n
            if n<255:
                yield bytes(pending);pending.clear()
        pos=q
    if pending:raise ValueError('Incomplete final packet')

def extract_nb_raw(filename,outfile):
    import struct
    it=iter(ogg_packets(filename.read_bytes()));h=next(it)
    if len(h)<80 or not h.startswith(b'Speex   '):raise ValueError('Not Speex file')
    # See SpeexHeader in libspeex: rate(36), mode(40), channels(48), bitrate(52), framesize(56), vbr(60), frames_per_packet(64)
    rate,mode,ver,channels,bitrate,frame,vbr,fpp,extra = struct.unpack_from('<9i',h,36)
    if (rate,mode,channels,bitrate,frame,vbr,fpp,extra)!=(8000,0,1,8000,160,0,1,0):
        raise ValueError('This tool requires NB 8kHz/8kbps mono CBR, one frame per packet, got '+str((rate,mode,channels,bitrate,frame,vbr,fpp,extra)))
    next(it) # Comment
    data=bytearray()
    for n,chunk in enumerate(it):
        if len(chunk)!=20 or chunk[0]>>3!=3: raise ValueError(f'Packet {n}: not Speex NB mode3, len={len(chunk)}')
        data+=chunk
    outfile.write_bytes(data)
    return len(data)//20

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',type=Path,default=Path(__file__).resolve().parent/'real_audio')
    parser.add_argument('--skip-seconds',type=float,default=2.0,help='Cut leading titles or silence when present')
    parser.add_argument('--duration',type=float,default=15.0,help='Clip seconds; 15 sec makes tests compact')
    parser.add_argument('--reuse',action='store_true',help='Reuse audio already downloaded to --out')
    parser.add_argument('--only',choices=['ru_male','ru_female','en_male','en_female'])
    args=parser.parse_args()
    if shutil.which('ffmpeg') is None:raise SystemExit('Install FFmpeg with libspeex encoder/decoder')
    args.out.mkdir(parents=True,exist_ok=True)
    for label,url in SOURCE_ITEMS:
        if args.only and label!=args.only:continue
        ogg=args.out/(label+'_original.ogg')
        if not (args.reuse and ogg.is_file()):
            print('Downloading',label, url,flush=True)
            download(url,ogg)
        wav8=args.out/(label+'_8k.wav')
        wav16=args.out/(label+'_16k.wav')
        for rate,out in [(8000,wav8),(16000,wav16)]:
            cmd('ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y','-ss',args.skip_seconds,
                '-i',ogg,'-t',args.duration,'-vn','-ac','1','-ar',rate,'-c:a','pcm_s16le',out)
        nb=args.out/(label+'_nb_8k_8kbps.ogg')
        wb=args.out/(label+'_wb_16k_9800bps.ogg')
        cmd('ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y','-i',wav8,'-c:a','libspeex','-b:a','8000','-frames_per_packet','1','-f','ogg',nb)
        cmd('ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y','-i',wav16,'-c:a','libspeex','-b:a','9800','-frames_per_packet','1','-f','ogg',wb)
        raw=args.out/(label+'_nb_8k_8kbps.spxraw')
        n=extract_nb_raw(nb,raw)
        print('OK:', label,n,'mode-3 packets; raw file',raw,flush=True)
    print('Completed. All original audio and test streams remain on your computer; observe CC BY-SA credits in REAL_SPEECH_SOURCES.md')
if __name__=='__main__':
    main()
