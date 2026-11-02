"""Shared normalized public source clips for LPX and Speex dialogue releases."""
import json
import math
import subprocess


def loudness(path,ffmpeg):
    command=[ffmpeg,'-hide_banner','-nostats','-i',str(path),'-af',
             'loudnorm=I=-18:TP=-1.5:LRA=11:print_format=json','-f','null','-']
    result=subprocess.run(command,capture_output=True,text=True,check=True)
    measure=json.JSONDecoder().raw_decode(result.stderr[result.stderr.rfind('{'):])[0]
    values=dict(lufs=float(measure['input_i']),truePeakDb=float(measure['input_tp']))
    if not all(math.isfinite(v) for v in values.values()):raise ValueError('Speech loudness is not finite')
    return values


def prepare_clips(recipe,names,source_files,output,ffmpeg):
    import numpy as np
    import soundfile as sf
    from scipy.signal import resample_poly
    from pcm16_wav import write_pcm16_wav
    prepared={};levels=[]
    for name,source in zip(names,source_files):
        pcm,rate=sf.read(source,dtype='int16')
        if pcm.ndim!=1 or not len(pcm):raise ValueError('Expected nonempty mono source')
        if rate!=8000:
            divisor=math.gcd(int(rate),8000)
            pcm=np.clip(np.rint(resample_poly(pcm.astype(float),8000//divisor,int(rate)//divisor)),-32768,32767).astype(np.int16)
        folder=output/name;folder.mkdir(parents=True,exist_ok=True)
        reference=folder/'reference.wav';write_pcm16_wav(reference,pcm)
        measured=loudness(reference,ffmpeg);prepared[name]=(pcm,folder,measured);levels.append(measured)
    target=min(float(recipe['targetLufs']),*(m['lufs']+recipe['truePeakLimitDb']-m['truePeakDb'] for m in levels))
    for name in names:
        pcm,folder,initial=prepared[name];gain_db=target-initial['lufs']
        adjusted=np.rint(pcm.astype(float)*10**(gain_db/20))
        if adjusted.min()<-32768 or adjusted.max()>32767:raise ValueError('Normalization would clip PCM16')
        adjusted=adjusted.astype(np.int16)
        normalized=folder/'normalized.wav';write_pcm16_wav(normalized,adjusted)
        before_encoding=loudness(normalized,ffmpeg)
        if before_encoding['truePeakDb']>recipe['truePeakLimitDb']+.1:raise ValueError('Normalized true peak exceeds the ceiling')
        prepared[name]=(adjusted,folder,initial,before_encoding,gain_db)
    spread=max(v[3]['lufs'] for v in prepared.values())-min(v[3]['lufs'] for v in prepared.values())
    if spread>.2:raise ValueError('Normalized dialogue sources do not match in loudness')
    return prepared,target


def assemble_dialogue(recipe,prepared):
    import numpy as np
    pieces=[];segments=[];at=0
    for item in recipe['sequence']:
        if set(item)=={'clip'}:
            name=item['clip'];piece=prepared[name][0];info=dict(kind='speech',clipId=name)
        elif set(item)=={'silenceSeconds'}:
            count=round(float(item['silenceSeconds'])*8000)
            if not 1<=count<=64000:raise ValueError('Pause must be 1..64000 samples')
            piece=np.zeros(count,dtype=np.int16);info=dict(kind='silence',seconds=count/8000)
        else:raise ValueError('Each segment must select a phrase or pause')
        pieces.append(piece);segments.append(dict(**info,startSample=at,samples=len(piece)));at+=len(piece)
    return np.concatenate(pieces),segments
