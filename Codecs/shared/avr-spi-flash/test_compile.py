"""Bounded real-vendor-header C99/C++11 API and object compilation checks."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sha=lambda raw:hashlib.sha256(raw).hexdigest()
PROBE='''#include "AvrSpiFlashReader.h"
typedef char check_offset_width[(sizeof(uint32_t)==4)?1:-1];
static AvrSpiFlashReader source;
int16_t (*read_callback)(void *)=avr_spi_flash_read;
int16_t reader_probe(uint32_t address,uint32_t bytes){
    avr_spi_flash_init(&source);
    if(!avr_spi_flash_begin(&source,address,bytes))return -1;
    int16_t result=read_callback(&source);
    avr_spi_flash_close(&source);
    return result;
}
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--avr-bin',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--write-provenance',action='store_true')
    args=parser.parse_args();args.avr_bin=args.avr_bin.resolve();args.output=args.output.resolve()
    if args.output.exists() or not args.output.is_relative_to(ROOT/'build'):
        parser.error('Use a fresh ignored build folder')
    args.output.mkdir(parents=True)
    header=HERE/'AvrSpiFlashReader.h';before=header.read_bytes()
    include=args.avr_bin.parent/'avr/include/avr'
    names=('io.h','iom328p.h','sfr_defs.h','common.h','portpins.h','version.h')
    headers={name:sha((include/name).read_bytes()) for name in names}
    version_text=(include/'version.h').read_text()
    avr_libc=re.search(r'__AVR_LIBC_VERSION_STRING__\s+"([^"]+)"',version_text).group(1)
    versions={};commands=[]
    for language,tool,standard in (('c','avr-gcc','c99'),('c++','avr-g++','gnu++11')):
        compiler=args.avr_bin/(tool+'.exe' if (args.avr_bin/(tool+'.exe')).exists() else tool)
        versions[language]=subprocess.check_output([str(compiler),'--version'],text=True).splitlines()[0]
        target=args.output/('reader-'+('c' if language=='c' else 'cpp')+'.o')
        flags=['-mmcu=atmega328p','-Os','-std='+standard,'-Wall','-Wextra','-Werror',
            '-ffunction-sections','-fdata-sections','-I'+str(HERE),'-x',language,'-c','-','-o',str(target)]
        if language=='c++':flags.insert(3,'-fno-exceptions')
        command=[str(compiler),*flags];commands.append(command)
        result=subprocess.run(command,input=PROBE.encode(),capture_output=True)
        (args.output/(tool+'.stdout.log')).write_bytes(result.stdout)
        (args.output/(tool+'.stderr.log')).write_bytes(result.stderr)
        if result.returncode:raise RuntimeError('AVR vendor-header compile check failed')
        assert target.is_file() and target.stat().st_size>0
    assert before==header.read_bytes() and headers=={name:sha((include/name).read_bytes()) for name in names}
    provenance=dict(schema='avr-spi-flash-reader-provenance-v1',target='ATmega328P',compiler_versions=versions,
        packaged_toolchain='AVR GCC7.3.0 / Atmel3.6.1 Arduino7 (existing project installation)',
        avr_libc_version=avr_libc,installed_headers_sha256=headers,
        register_source='Installed avr-libc avr/io.h selects iom328p.h using compiler MCU defines; headers reused unchanged',
        official_device_reference=dict(document='7810D-AVR-01/15',table='18-5',
            url='https://ww1.microchip.com/downloads/en/DeviceDoc/Atmel-7810-Automotive-Microcontrollers-ATmega328P_Datasheet.pdf'),
        clock='SPI2X=1, SPR1=SPR0=0 => F_CPU/2; sixteen CPU cycles per byte',
        driver_sha256=sha(before),bounded_checks=dict(c99_object=True,cpp11_object=True,callback_signature=True,
            address_and_length_bits=32,new_linked_images=0,playback_support_claim=False))
    (args.output/'receipt-private.json').write_bytes(json.dumps(dict(status='PASS',commands=commands,provenance=provenance),indent=2).encode()+b'\n')
    if args.write_provenance:(HERE/'PROVENANCE.json').write_bytes(json.dumps(provenance,indent=2).encode()+b'\n')
    print(json.dumps(dict(status='PASS',vendor_header_c99_cpp11_objects=2,new_linked_images=0,avr_libc_version=avr_libc)))


if __name__=='__main__':main()
