"""Exhaustively compare the portable C producer gain with independent integers."""
from pathlib import Path
import argparse
import subprocess
from pwm_output_level import apply_gain,choose_gain,describe_level

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cc',default='g++');p.add_argument('--wsl')
    args=p.parse_args();folder=ROOT/'build/output-range/conformance';folder.mkdir(parents=True,exist_ok=True)
    path=lambda x:('/mnt/'+x.drive[0].lower()+'/'+'/'.join(x.parts[1:])) if args.wsl and x.drive else str(x)
    header=path(ROOT/'Codecs/common/pwm_gain.h')
    text='#include <stdio.h>\n'
    for n in range(128,256):
        text+=f'#define PWM_GAIN_Q7 {n}\n#define micromusic_pwm_gain gain{n}\n#include "{header}"\n'
        text+='#undef MICROMUSIC_PWM_GAIN_H\n#undef PWM_GAIN_Q7\n#undef micromusic_pwm_gain\n'
    text+='int main(){\n'
    for n in range(128,256):text+=f'for(unsigned v=0;v<256;v++)putchar(gain{n}(v));\n'
    text+='}\n';source=folder/'all.cpp';source.write_text(text,encoding='utf-8',newline='\n')
    binary=folder/'all';prefix=['wsl','-d',args.wsl,'--'] if args.wsl else []
    subprocess.run([*prefix,args.cc,'-std=c++11','-O2',path(source),'-o',path(binary)],check=True,capture_output=True)
    actual=subprocess.check_output([*prefix,path(binary)])
    expected=bytes(max(0,min(255,((v-128)*n+64)//128+128)) for n in range(128,256) for v in range(256))
    assert actual==expected and len(actual)==32768
    for n in range(128,256):
        output=actual[(n-128)*256:(n-127)*256]
        assert output==apply_gain(bytes(range(256)),n) and output[128]==128
        assert list(output)==sorted(output)
    for lo in range(0,128):
        for hi in range(129,256):
            pcm=bytes((lo,128,hi));n=choose_gain(pcm);level=describe_level(pcm,n)
            assert level['saturatedSamples']==0
            if n>128:
                result=apply_gain(pcm,n);assert 2<=min(result)<=max(result)<=254
                if n<255:assert min(apply_gain(pcm,n+1))<2 or max(apply_gain(pcm,n+1))>254
    assert choose_gain(bytes([128])*100)==128
    print('PASS 32768 C/integer pairs, every bipolar extrema pair, exact silence, saturation and maximal safe gain')


if __name__=='__main__':main()
