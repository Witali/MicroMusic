"""Opt-in L4HY v3 metadata experiment, retaining all v2 excitation modes.

Feature bits live in header flags; arithmetic, LSF values and q do not change.
The MCU must explicitly enable every used bit with LPX4_V3_FEATURES.
"""
from lpx4 import BitWriter, signed_from_z, mapped
from lossless_repack import layout, copy_bits
from rice_v4_reference import write_scale, putplane, plane_cost
from rice_v7 import absolute_lsf10

SCALE_REPEAT=4
WIDTH_REPEAT=8
SUBHEADER_REPEAT=16
ZERO_HEADERS=32
LSF_RICE=64
ALL_FEATURES=124


def put_lsf_rice(w,byte,k):
    delta=byte-256 if byte>=128 else byte;z=mapped(delta);quotient=z>>k
    if quotient>=8:
        for _ in range(8):w.put(0,1)
        w.put(byte,8)
    else:
        for _ in range(quotient):w.put(0,1)
        w.put(1,1)
        if k:w.put(z&((1<<k)-1),k)


def get_lsf_rice(r,k):
    quotient=0
    while quotient<8 and not r.get(1):quotient+=1
    if quotient==8:return r.get(8)
    return signed_from_z((quotient<<k)|(r.get(k) if k else 0))&255


def put_frame(w,frame,features):
    if frame[0]==0:w.put(0,1);return
    w.put(1,1)
    if frame[0]==5:
        w.put(0,1)
        for v in absolute_lsf10(frame[1:]):w.put(v&255,8);w.put(v>>8,2)
        return
    if frame[0]!=6:raise ValueError('Unsupported frame')
    w.put(1,1);delta=frame[1:]
    if not features&LSF_RICE:
        raw=80<=plane_cost(delta);w.put(int(raw),1)
        for byte in delta:
            if raw:w.put(byte,8)
            else:putplane(w,byte)
        return
    options=[]
    for mode in range(4):
        trial=BitWriter()
        for byte in delta:
            if mode==0:putplane(trial,byte)
            elif mode==1:trial.put(byte,8)
            else:put_lsf_rice(trial,byte,0 if mode==2 else 2)
        options.append((trial.total,mode))
    mode=min(options)[1];w.put(mode,2)
    for byte in delta:
        if mode==0:putplane(w,byte)
        elif mode==1:w.put(byte,8)
        else:put_lsf_rice(w,byte,0 if mode==2 else 2)


def pack(blob,features=ALL_FEATURES):
    if features&~ALL_FEATURES or features<0:raise ValueError('Unknown compact feature')
    if blob[:6]!=b'L4HY\x02\x03':raise ValueError('Input must be L4HY v2')
    frames,blocks,q,spans=layout(blob)
    header=bytearray(blob[:20]);header[4]=3;header[5]=3|features
    w=BitWriter();oldscale=0;oldwidth=0;oldheader=('direct',0)
    counts={'same_scale':0,'same_width':0,'same_subheader':0,'zero_blocks':0}
    for index,(block,span) in enumerate(zip(blocks,spans)):
        if span.frame:put_frame(w,frames[index//2],features)
        width=block['bits']
        if features&WIDTH_REPEAT:
            same=oldwidth==width;w.put(int(not same),1);counts['same_width']+=int(same)
            if not same:w.put(width,3)
        else:w.put(width,3)
        oldwidth=width
        if not width and features&ZERO_HEADERS:
            counts['zero_blocks']+=1;oldheader=('direct',0)
            continue
        value=block['scale']
        if features&SCALE_REPEAT:
            same=value==oldscale;w.put(int(not same),1);counts['same_scale']+=int(same)
            if not same:write_scale(w,oldscale,value)
        else:write_scale(w,oldscale,value)
        oldscale=value
        for chunk in span.chunks:
            descriptor=chunk.mode if chunk.mode[0]!='sparse' else chunk.mode[:3]
            same=descriptor==oldheader
            if features&SUBHEADER_REPEAT:
                w.put(int(not same),1);counts['same_subheader']+=int(same)
            if not (same and features&SUBHEADER_REPEAT):
                copy_bits(w,blob,chunk.start,chunk.payload-(4 if chunk.mode[0]=='sparse' else 0))
            if chunk.mode[0]=='sparse':w.put(chunk.mode[3],4)
            copy_bits(w,blob,chunk.payload,chunk.end)
            oldheader=descriptor
    bits=w.total;w.aligned();result=bytes(header)+w.get()
    return result,{'features':features,'bytes_before':len(blob),'bytes_after':len(result),
                   'payload_bits':bits,**counts}


def main():
    import argparse
    import hashlib
    import json
    from pathlib import Path
    import numpy as np
    from batch_decoder import BatchSession
    from output_paths import protect_outputs
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('input',type=Path);ap.add_argument('output',type=Path)
    ap.add_argument('--features',type=int,required=True,help='24: width/subheader; 40: width/zero; 124: all experiments')
    ap.add_argument('--report',type=Path);ap.add_argument('--timing-work',type=Path)
    ap.add_argument('--avr-bin',type=Path);ap.add_argument('--sim-runner',type=Path)
    ap.add_argument('--sim-lib-dir',type=Path);ap.add_argument('--wsl')
    a=ap.parse_args()
    if not a.features or a.features&~ALL_FEATURES:ap.error('Provide a nonzero supported --features mask')
    if any((a.avr_bin,a.sim_runner,a.timing_work)) and not all((a.avr_bin,a.sim_runner,a.timing_work)):
        ap.error('Timing/Flash gate needs --avr-bin, --sim-runner and --timing-work')
    protect_outputs([a.input],[a.output]+([a.report] if a.report else []))
    blob=a.input.read_bytes();candidate,report=pack(blob,a.features)
    n=int.from_bytes(blob[8:12],'little')
    with BatchSession('batch',v3_features=a.features) as dec:
        before=dec.decode_one_s16(blob,n);after=dec.decode_one_s16(candidate,n)
        if before is None or after is None or not np.array_equal(before,after):
            raise AssertionError('Compact repack changed native PCM16')
    report.update(native_pcm16_exact=True,pcm16_sha256=hashlib.sha256(after.astype('<i2').tobytes()).hexdigest())
    accepted=True
    if a.timing_work:
        from profile_avr import run as profile
        protect_outputs([a.input],[a.timing_work/'v2.l4hy',a.timing_work/'v3.l4hy'])
        a.timing_work.mkdir(parents=True,exist_ok=True)
        results=[]
        for label,data,features in (('v2',blob,0),('v3',candidate,a.features)):
            path=a.timing_work/(label+'.l4hy');path.write_bytes(data)
            results.append(profile(path,a.timing_work/label,a.avr_bin,a.sim_runner,a.sim_lib_dir,a.wsl,
                                   enable_asm=True,v3_features=features))
        b,c=results
        accepted=(c['underruns']==0 and c['flash_bytes']<=b['flash_bytes'] and
                  c['mean_decode_wall_cycles']<=b['mean_decode_wall_cycles'] and
                  c['decode_wall_cycles_max_160']<=b['decode_wall_cycles_max_160'])
        report.update(before=b,candidate=c,accepted_total_flash_and_timing=accepted)
    result=candidate if accepted else blob
    report.update(output_version=result[4],output_bytes=len(result),
                  input_sha256=hashlib.sha256(blob).hexdigest(),output_sha256=hashlib.sha256(result).hexdigest(),
                  avr_cycles_measured=bool(a.timing_work))
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_bytes(result)
    if a.report:
        a.report.parent.mkdir(parents=True,exist_ok=True)
        a.report.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
