#!/usr/bin/env python3
"""Build the SPI-input player and optional host-only W25Q128 WASM model."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build
import build_wb

ROOT = build.ROOT
REPO = ROOT.parents[2]
MODEL = REPO/'tools/spi-flash-model'
DRIVER = REPO/'Codecs/shared/avr-spi-flash'


def digest(path, text=False):
    data = path.read_bytes()
    return hashlib.sha256(data.replace(b'\r\n', b'\n') if text else data).hexdigest()


def model(compiler, out, sysroot=None):
    out.mkdir(parents=True, exist_ok=True)
    sysroot = sysroot or Path(compiler).resolve().parents[1]/'emscripten/cache/sysroot'
    exports = ['speex_spi_image', 'speex_spi_init', 'speex_spi_select', 'speex_spi_transfer', 'speex_spi_stat']
    build.run([compiler, '--target=wasm32', '--sysroot='+str(sysroot), '-std=c11', '-O2', '-fno-builtin',
               '-nostdlib', '-I'+str(MODEL), MODEL/'w25q128_readonly.c', ROOT/'tests/spi_model_wasm.c',
               '-Wl,--no-entry', *['-Wl,--export='+name for name in exports],
               '-Wl,--initial-memory=33554432', '-Wl,--max-memory=33554432', '-o', out/'model.wasm'])
    print('Built host-only model:', digest(out/'model.wasm'))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--avr-gcc')
    p.add_argument('--stream', type=Path, help='Uniform raw Speex packets, not Ogg')
    p.add_argument('--wideband', action='store_true')
    p.add_argument('--backend', choices=['c', 'asm'], default='c')
    p.add_argument('--low-rates', type=int, choices=range(8), default=7)
    p.add_argument('--enable-nb4', action='store_true')
    p.add_argument('--address', type=lambda value: int(value, 0), default=0xff80)
    p.add_argument('--capture-pcm', action='store_true', help='Test-only s16 observation; no transport shortcut')
    p.add_argument('--out', type=Path, default=ROOT/'build/spi-player')
    p.add_argument('--driver-dir', type=Path, default=DRIVER, help='Shared AVR SPI reader include directory')
    p.add_argument('--image-out', type=Path, help='Create a new 16 MiB programmer image, filled with 0xff elsewhere')
    p.add_argument('--wasm-clang', help='Also build the host-only protocol model')
    p.add_argument('--wasm-sysroot', type=Path)
    args = p.parse_args()
    if args.image_out and not args.stream: p.error('--image-out requires --stream')
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if args.wasm_clang:
        model(args.wasm_clang, out, args.wasm_sysroot)
    if not args.stream:
        if args.wasm_clang: return
        p.error('--stream or --wasm-clang is required')
    if not args.avr_gcc: p.error('--stream requires --avr-gcc')
    data = args.stream.read_bytes()
    mode = data[0] >> 3 if data else -1
    bits = build.MODE_BITS.get(mode, 0)
    width = (bits+(36 if args.wideband else 0)+7)//8 if bits else 0
    if not width or len(data) % width or any(data[i] >> 3 != mode for i in range(0, len(data), width)):
        p.error('Expected complete uniform packets in a supported mode')
    if mode in build.LOW_FEATURE and not args.low_rates & build.LOW_FEATURE[mode]:
        p.error('The packet mode is not enabled by --low-rates')
    if mode == 4 and not args.enable_nb4: p.error('NB4 requires --enable-nb4')
    if args.wideband and any((int.from_bytes(data[i:i+width], 'big') >> (width*8-bits-4)) & 15 != 9
                            for i in range(0, len(data), width)):
        p.error('Only HB1 wideband packets are supported')
    if not 0 <= args.address < 16777216 or len(data) > 16777216-args.address:
        p.error('Address and stream must fit a 16 MiB W25Q128 without wrapping')
    if args.image_out:
        image = bytearray(b'\xff') * 16777216
        image[args.address:args.address+len(data)] = data
        args.image_out.parent.mkdir(parents=True, exist_ok=True)
        with args.image_out.open('xb') as target:
            target.write(image)
    frames = len(data)//width
    (out/'sample.h').write_text('#define SPEEX_SAMPLE_PACKET_BYTES '+str(width)+
        '\n#define SPEEX_SAMPLE_FRAMES 1\nstatic const uint8_t sample_data[1] PROGMEM={0};\n')
    (out/'spi_sample.h').write_text('#include <stdint.h>\n'+
        '#define SPEEX_SPI_ADDRESS UINT32_C('+str(args.address)+')\n'+
        '#define SPEEX_SPI_BYTES UINT32_C('+str(len(data))+')\n'+
        '#define SPEEX_SPI_FRAME_COUNT UINT32_C('+str(frames)+')\n')
    source = build_wb.prepare()
    options = build_wb.flags(source, args.backend, args.enable_nb4, args.low_rates)
    if not args.wideband:
        options.remove('-DSPEEX_ENABLE_WB1=1')
        options.append('-DSPEEX_AVR_OUTPUT_HOOK')
    options += ['-Os', '-flto', '-mmcu=atmega328p', '-mcall-prologues', '-mrelax',
                '-ffunction-sections', '-fdata-sections', '-I'+str(out), '-I'+str(args.driver_dir.resolve()),
                '-DSPEEX_SPI_WIDEBAND='+str(int(args.wideband)),
                '-DSPEEX_SPI_CAPTURE_PCM='+str(int(args.capture_pcm))]
    units = build_wb.sources(source) if args.wideband else [
        source/'libspeex'/(name+'.c') for name in build.PROFILE_SOURCES]+[
        ROOT/'src'/name for name in ['speex_avr.c', 'bits.c', 'lowrate_noise.c']]
    if args.backend == 'asm':
        units += [ROOT/'src'/s for s in build.ASM_SOURCES+(build_wb.ASM_SOURCES if args.wideband else [])]
    exe = out/'player.elf'
    build.run([args.avr_gcc, *options, *units, ROOT/'examples/spi_flash_player.c',
               '-Wl,--gc-sections', '-o', exe])
    prefix = str(Path(args.avr_gcc).with_name('avr-'))
    ext = '.exe' if args.avr_gcc.endswith('.exe') else ''
    for kind, suffix in [('binary', 'bin'), ('ihex', 'hex')]:
        build.run([prefix+'objcopy'+ext, '-O', kind, '-R', '.eeprom', exe, out/('player.'+suffix)])
    assert (out/'player.bin').stat().st_size <= 32768
    symbols = subprocess.check_output([prefix+'nm'+ext, '-n', exe], text=True)
    (out/'symbols.txt').write_text(symbols)
    assert ' sample_data' not in symbols and 'speex_embedded_player_unused_main' not in symbols
    metadata = dict(backend=args.backend, wideband=args.wideband, capturePcm=args.capture_pcm,
        lowRates=args.low_rates, nb4Enabled=args.enable_nb4, packetBytes=width, frames=frames,
        flashAddress=args.address, streamBytes=len(data), inputSha256=digest(args.stream),
        binarySha256=digest(out/'player.bin'), cpuHz=16000000, spiHz=8000000,
        csPort='B', csBit=2, command=11,
        driverSha256=digest(args.driver_dir/'AvrSpiFlashReader.h', text=True))
    (out/'input.json').write_bytes((json.dumps(metadata, indent=2)+'\n').encode())
    build.run([prefix+'size'+ext, '-C', '--mcu=atmega328p', exe])


if __name__ == '__main__':
    main()
