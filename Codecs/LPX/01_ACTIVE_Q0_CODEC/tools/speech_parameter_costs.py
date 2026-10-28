"""Hypothetical parameter bit costs only; no new audio format or decoder.

The approved thirteen syntax sketches retain every stored parameter. Existing
v5 body bits outside the15-bit tuples are counted from the actual source stream,
without repacking/canonicalizing flags, markers, Rice choices or padding.
"""
from __future__ import annotations

from dataclasses import asdict,dataclass
import hashlib
from numbers import Integral
import speech_compact as compact
from lpx4 import BitReader
from speech_parameter_histograms import FIELDS,parameter_codes


@dataclass(frozen=True)
class Method:
    selector: int
    name: str
    kind: str
    mask: int
    k: int | None = None


METHODS=tuple([Method(mask,f'repeat-mask{mask}','repeat',mask) for mask in range(1,8)]+
    [Method(8+i,f'rice-mask{mask}-k{k}','rice',mask,k) for i,(mask,k) in enumerate((mask,k) for mask in (5,7) for k in (0,1,2))])
HEADER_BYTES=23  # Existing22-byte v5-shaped header plus one new method selector.


def inspect_stream(blob):
    """Count actual consumed source bits; untouched fields are never normalized."""
    blob=bytes(blob);values=compact.unpack(blob)
    n,profile,spectra,params,pulses,pre,bright,extras=values
    reader=BitReader(blob[22:]);old=None;read_params=[];marker_bits=extra_bits=0
    for frame in range(len(spectra)):
        vector=compact.get_spectrum(reader,old,5 if profile==4 else 6)
        if vector!=spectra[frame]:raise AssertionError('Independent bit cursor spectrum mismatch')
        old=vector
        for half in range(2):
            read_params.append((reader.get(5),reader.get(7),reader.get(3)))
            for chunk in range(4):
                reader.get(10 if profile==4 else 17)
                if blob[5]&128:
                    marker_bits+=1
                    if reader.get(1):reader.get(10);extra_bits+=10
    if read_params!=parameter_codes(params):raise AssertionError('Independent bit cursor parameter mismatch')
    payload_bits=reader.o*8-reader.n;payload_bytes=len(blob)-22
    if reader.o!=payload_bytes or reader.acc or not 0<=reader.n<8:
        raise AssertionError('Independent payload/padding cursor mismatch')
    parameter_bits=len(params)*15
    return {'source_sha256':hashlib.sha256(blob).hexdigest(),'samples':n,'profile':profile,'stored_tuples':len(params),'audible_tuples':(n+159)//160,
        'unplayed_stored_tuples':len(params)-(n+159)//160,'current_header_bytes':22,
        'current_payload_bits':payload_bits,'current_parameter_bits':parameter_bits,
        'untouched_payload_bits':payload_bits-parameter_bits,'current_padding_bits':reader.n,
        'current_file_bytes':len(blob),'source_extras_flag':bool(blob[5]&128),
        'source_extra_marker_bits':marker_bits,'source_extra_value_bits':extra_bits,
        'params':params}


def parameter_bits(params,method):
    """Exact lengths under one predeclared syntax; no bitstream is emitted.

    First tuple is always15 absolute bits. Repeat-selected fields use one flag
    then their old absolute width only on change. Rice-selected fields use
    zigzag(delta), k common to those fields, q<8 normal q+1+k bits, or exactly
    eight zero escape bits followed by the complete absolute field width.
    Every next tuple updates history, including gain0's unused lag and tails.
    """
    if method not in METHODS:raise ValueError('Expected a predeclared hypothetical method')
    params=list(params)
    if any(len(row)!=3 or any(isinstance(v,bool) or not isinstance(v,Integral) for v in row)
           or not 0<=row[0]<=31 or not 18<=row[1]<=145 or not 0<=row[2]<=14 or row[2]%2 for row in params):
        raise ValueError('Expected exact legal v5 parameter tuples')
    packets=parameter_codes(params)
    if not packets:raise ValueError('Expected at least one stored tuple')
    if any(not 0<=value<(1<<width) for packet in packets for value,(_,width) in zip(packet,FIELDS)):
        raise ValueError('Parameter outside actual stored field domain')
    bits=15;stats={name:{'width':width,'initial_absolute_bits':width,'transition_bits':0,
        'repeats':0,'normal_rice':0,'absolute_escapes':0,'absolute_transitions':0} for name,width in FIELDS}
    for previous,packet in zip(packets,packets[1:]):
        for i,(name,width) in enumerate(FIELDS):
            value=packet[i];old=previous[i];selected=bool(method.mask&(1<<i));field=stats[name]
            if not selected:cost=width;field['absolute_transitions']+=1
            elif method.kind=='repeat':
                repeat=value==old;cost=1+(0 if repeat else width)
                field['repeats']+=int(repeat);field['absolute_transitions']+=int(not repeat)
            else:
                delta=value-old;z=2*delta if delta>=0 else -2*delta-1;q=z>>method.k
                if q<8:cost=q+1+method.k;field['normal_rice']+=1
                else:cost=8+width;field['absolute_escapes']+=1
            bits+=cost;field['transition_bits']+=cost
    return {'bits':bits,'initial_absolute_bits':15,'tuples':len(packets),'fields':stats}


def stream_cost(blob,method,inspection=None):
    """Exact complete hypothetical stored bytes under the declared assumptions."""
    info=inspect_stream(blob) if inspection is None else inspection
    if info['source_sha256']!=hashlib.sha256(bytes(blob)).hexdigest():raise ValueError('Inspection belongs to a different source stream')
    parameters=parameter_bits(info['params'],method)
    payload=info['untouched_payload_bits']+parameters['bits'];padding=(-payload)%8
    size=HEADER_BYTES+(payload+padding)//8
    saving=info['current_file_bytes']-size
    return {'method':asdict(method),'samples':info['samples'],'profile':info['profile'],
        'stored_tuples':info['stored_tuples'],'unplayed_stored_tuples':info['unplayed_stored_tuples'],
        'current_file_bytes':info['current_file_bytes'],'current_payload_bits':info['current_payload_bits'],
        'current_parameter_bits':info['current_parameter_bits'],'current_padding_bits':info['current_padding_bits'],
        'source_extras_flag':info['source_extras_flag'],'source_extra_marker_bits':info['source_extra_marker_bits'],
        'source_extra_value_bits':info['source_extra_value_bits'],'untouched_payload_bits':info['untouched_payload_bits'],
        'proposed_header_bytes':HEADER_BYTES,'additional_selector_bytes':1,
        'proposed_parameter_bits':parameters['bits'],'proposed_payload_bits':payload,
        'proposed_padding_bits':padding,'proposed_file_bytes':size,'whole_stream_saved_bytes':saving,
        'same_rom_api_size_fits':size<=65535,'parameter_detail':parameters,
        'fallback_v5_or_proposed_bytes':min(info['current_file_bytes'],size),
        'format_implemented':False,'decoder_flash_measured':False}


def chain_cost(streams,method,inspections=None):
    """Every segment gets its own first absolute tuple, header and final padding."""
    if isinstance(streams,(bytes,bytearray,str)):raise ValueError('Expected ordered complete streams')
    streams=list(streams)
    if not streams:raise ValueError('Expected at least one complete stream')
    if inspections is None:inspections=[None]*len(streams)
    if len(inspections)!=len(streams):raise ValueError('Expected one inspection per stream')
    costs=[stream_cost(blob,method,info) for blob,info in zip(streams,inspections)]
    old=sum(c['current_file_bytes'] for c in costs);new=sum(c['proposed_file_bytes'] for c in costs)
    saved=old-new
    return {'method':asdict(method),'segments':len(costs),'current_file_bytes':old,'proposed_file_bytes':new,
        'whole_stream_saved_bytes':saved,'added_decoder_flash_data_upper_bound_bytes':saved,
        'nonnegative_decoder_growth_possible_from_data_alone':saved>=0,
        'fallback_v5_or_proposed_bytes':sum(c['fallback_v5_or_proposed_bytes'] for c in costs),
        'fallback_data_only_upper_bound_bytes':sum(max(0,c['whole_stream_saved_bytes']) for c in costs),
        'segment_costs':costs,'format_implemented':False,'decoder_flash_measured':False}
