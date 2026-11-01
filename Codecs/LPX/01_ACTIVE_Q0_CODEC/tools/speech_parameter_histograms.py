"""Anonymous v5 parameter repeat/delta measurements; no new format or encoder."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path

import speech_compact as compact


FIELDS=(('scale',5),('lag',7),('gain_code',3))


def parameter_codes(params):
    """Validated v5 tuples in exact stored units, including otherwise unused lag."""
    return [(int(scale),int(lag)-18,int(gain)//2) for scale,lag,gain in params]


def _counter(counter):
    return {str(key):counter[key] for key in sorted(counter)}


def parameter_histograms(streams):
    """Measure each stream independently; never invent cross-segment repeats.

    Gain is measured in its actual stored code units (gain /2), and lag deltas
    use sample units. Both stored packets and packets beginning before EOS are
    reported so mandatory unplayed tail fields cannot masquerade as savings.
    """
    groups={name:{'packets':0,'first_packets':0,'transitions':0,'tuple_repeats':0,
        'fields':{field:{'absolute':Counter(),'delta':Counter(),'repeats':0} for field,_ in FIELDS}}
        for name in ('stored','audible')}
    stream_count=0;samples=0
    for blob in streams:
        n,profile,spectra,params,pulses,pre,bright,extras=compact.unpack(bytes(blob))
        stream_count+=1;samples+=n
        coded=parameter_codes(params)
        for label,packets in (('stored',coded),('audible',coded[:(n+159)//160])):
            group=groups[label];group['packets']+=len(packets);group['first_packets']+=1
            for i,packet in enumerate(packets):
                for j,(field,_) in enumerate(FIELDS):group['fields'][field]['absolute'][packet[j]]+=1
                if not i:continue
                previous=packets[i-1];group['transitions']+=1
                group['tuple_repeats']+=int(packet==previous)
                for j,(field,_) in enumerate(FIELDS):
                    stats=group['fields'][field];delta=packet[j]-previous[j]
                    stats['delta'][delta]+=1;stats['repeats']+=int(delta==0)
    for group in groups.values():
        packets=group['packets'];first=group['first_packets'];transitions=group['transitions'];repeat=group['tuple_repeats']
        group['current_fixed_parameter_bits']=15*packets
        # Arithmetic sketches only: first packet stays absolute; every later
        # tuple/field gets one marker, and changes retain its old absolute bits.
        group['hypothetical_tuple_repeat_bits']=first*15+transitions+(transitions-repeat)*15
        group['hypothetical_independent_field_repeat_bits']=first*15+sum(transitions+(transitions-group['fields'][field]['repeats'])*width for field,width in FIELDS)
        for field,width in FIELDS:
            stats=group['fields'][field];stats['stored_width_bits']=width
            stats['absolute']=_counter(stats['absolute']);stats['delta']=_counter(stats['delta'])
    return {'schema':'lpx-v5-parameter-histograms-v1','streams':stream_count,'samples':samples,
        'stored_unplayed_packets':groups['stored']['packets']-groups['audible']['packets'],
        'groups':groups,'format_implemented':False,'mcu_flash_claim_bytes':0,
        'scope':'Parameter layer only. Actual stored v5 is15 bits/160samples. Streams reset independently. Lag absolute codes subtract18; deltas remain sample units. Repeat-marker costs are arithmetic sketches, excluding any new-format headers, decoder code, tails or byte padding. Delta histograms do not imply a selected delta syntax.'}


def main():
    from output_paths import protect_outputs
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('streams',nargs='+',type=Path);parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args();protect_outputs(args.streams,[args.output])
    result=parameter_histograms(path.read_bytes() for path in args.streams)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'streams':result['streams'],'samples':result['samples'],'format_implemented':False}))


if __name__=='__main__':main()
