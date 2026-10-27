"""Shared PCM error, fixed PWM and Ogg byte accounting for codec comparisons."""
import re
import warnings
import numpy as np
from scipy.signal import correlate


_STOI_INSUFFICIENT_FRAMES = (
    'Not enough STFT frames to compute intermediate intelligibility measure '
    'after removing silent frames. Returning 1e-5. Please check you wav files')


def error_metrics(reference, decoded, speech=False, rate=8000):
    x=np.asarray(reference,dtype=np.int64);y=np.asarray(decoded,dtype=np.int64)
    if x.ndim!=1 or x.shape!=y.shape or not len(x):raise ValueError('Equal nonempty mono arrays required')
    error=y-x;power=float(np.dot(x,x));sse=float(np.dot(error,error))
    index=int(np.argmax(np.abs(error)));peak=int(abs(error[index]))
    result={'samples':len(x),'reference_energy':power,'error_energy':sse,
        'ser_db':float(10*np.log10(power/sse)) if power and sse else None,
        'ser_status':'finite' if power and sse else 'perfect' if not sse else 'zero_reference',
        'rmse_pcm16':float(np.sqrt(sse/len(x))), 'max_abs_error_pcm16':peak,
        'max_abs_error_percent_fs':peak*100/32768,'max_error_signed_pcm16':int(error[index]),
        'max_error_sample':index,'max_error_seconds':index/rate,
        'stoi':None}
    if speech and power:
        from pystoi import stoi
        from pystoi.stoi import FS, N, N_FRAME
        # Both pystoi framing passes exclude a window ending exactly at the
        # array boundary. Even before silence removal, N final STFT frames
        # therefore need N_FRAME + N*(N_FRAME//2) + 1 resampled samples.
        # resample_poly returns ceil(input_samples*FS/rate); use an exact
        # integer inequality, and leave invalid rates to pystoi as before.
        minimum=N_FRAME+N*(N_FRAME//2)
        if rate>0 and int(rate)==rate and len(x)*FS<=minimum*int(rate):return result
        # pystoi returns a numeric sentinel for insufficient active frames.
        # Identify that specific warning, not its value: a valid score may
        # also be 1e-5. Other warnings retain the caller's warning policy.
        with warnings.catch_warnings():
            warnings.filterwarnings('error',message='^'+re.escape(_STOI_INSUFFICIENT_FRAMES)+'$',
                                    category=RuntimeWarning,module=r'^pystoi\.stoi$')
            try:
                result['stoi']=float(stoi(x.astype(float)/32768,y.astype(float)/32768,rate))
            except RuntimeWarning as warning:
                origin=warning.__traceback__
                while origin.tb_next is not None:origin=origin.tb_next
                if (str(warning)!=_STOI_INSUFFICIENT_FRAMES or
                        origin.tb_frame.f_globals.get('__name__')!='pystoi.stoi'):raise
    return result


def pwm_duties(pcm):
    """The common LPX gain130/round1 transfer; no fitted gain/normalization.

    Recreate Q14 from native PCM16 exactly (including saturated +32767).
    The same fixed half-LSB rounding applies to odd standard-decoder samples.
    """
    q14=(np.asarray(pcm,dtype=np.int64)+1)//2
    return np.clip(128+((q14*130+8192)>>14),0,255).astype(np.uint8)


def pwm_pcm16(pcm):
    return (pwm_duties(pcm).astype(np.int32)-128)*256


def delay_samples(reference,decoded,rate=8000,limit_ms=60):
    x=np.asarray(reference,dtype=np.float64);y=np.asarray(decoded,dtype=np.float64)
    if len(y)<len(x):raise ValueError('Short decoded output')
    limit=min(round(rate*limit_ms/1000),len(y)-len(x))
    if not np.any(x) or not limit:return 0
    # Each tested shift retains the entire reference, including both edges.
    scores=correlate(y[:len(x)+limit],x,mode='valid',method='fft')
    return int(np.argmax(scores[:limit+1]))


def compare(reference,decoded,speech=False,known_delay=None):
    n=len(reference)
    if len(decoded)<n:raise ValueError('Short decoded output')
    delay=delay_samples(reference,decoded) if known_delay is None else int(known_delay)
    if delay<0 or delay+n>len(decoded):raise ValueError('Delay does not preserve full reference')
    aligned=np.asarray(decoded)[delay:delay+n]
    return {'delay_samples':delay,'delay_ms':delay/8,
        'unaligned_pcm16':error_metrics(reference,np.asarray(decoded)[:n],speech),
        'aligned_pcm16':error_metrics(reference,aligned,speech),
        'aligned_pwm8':error_metrics(reference,pwm_pcm16(aligned),speech)},aligned


def ogg_accounting(blob):
    """Single logical Ogg stream: setup, comments, audio and page bytes.

    The required Vorbis codebook header remains explicitly counted. This is
    byte accounting of trusted encoder output, not a replacement Ogg decoder.
    """
    packets=[];pending=bytearray();pos=0;overhead=0;serial=None
    while pos<len(blob):
        if blob[pos:pos+5]!=b'OggS\x00' or pos+27>len(blob):raise ValueError('Invalid Ogg page')
        count=blob[pos+26];end=pos+27+count
        if end>len(blob):raise ValueError('Truncated lacing')
        current=blob[pos+14:pos+18]
        if serial is None:serial=current
        elif serial!=current:raise ValueError('Multiple logical streams unsupported')
        if bool(blob[pos+5]&1)!=bool(pending):raise ValueError('Invalid continuation')
        lace=blob[pos+27:end];cursor=end;overhead+=27+count
        for size in lace:
            if cursor+size>len(blob):raise ValueError('Truncated packet')
            pending.extend(blob[cursor:cursor+size]);cursor+=size
            if size<255:packets.append(bytes(pending));pending.clear()
        pos=cursor
    if pending:raise ValueError('Unterminated packet')
    if not packets:raise ValueError('Empty Ogg')
    if packets[0].startswith(b'OpusHead'):codec='opus';setup=(0,);comments=(1,)
    elif packets[0].startswith(b'Speex   '):codec='speex';setup=(0,);comments=(1,)
    elif packets[0].startswith(b'\x01vorbis'):codec='vorbis';setup=(0,2);comments=(1,)
    else:raise ValueError('Unsupported Ogg codec')
    if len(packets)<=max(setup+comments):raise ValueError('Missing codec headers')
    header=sum(len(packets[i]) for i in setup);tags=sum(len(packets[i]) for i in comments)
    audio=sum(len(p) for i,p in enumerate(packets) if i not in setup+comments)
    if audio+header+tags+overhead!=len(blob):raise AssertionError('Byte accounting mismatch')
    return {'codec':codec,'file_bytes':len(blob),'audio_packet_bytes':audio,
        'codec_setup_bytes':header,'comment_bytes':tags,'container_overhead_bytes':overhead,
        'audio_packets':len(packets)-len(setup)-len(comments)}
