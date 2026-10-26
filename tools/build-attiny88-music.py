"""Port the retained ATtiny13A music arrangements to a real ATtiny88.

Requires GNU AVR binutils/GCC. Musical commands remain byte-exact. DDS words
are regenerated for the selected board's CPU clock /512; rational clocks keep
the original control/envelope cadence. The MH-ET LIVE USB variant embeds the
64-byte EEPROM bank in Flash because Micronucleus uploads application Flash.
No MIDI binaries or SoundFonts are used.
"""
from pathlib import Path
import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'ATtiny13A/Music/variants'
OUTPUT = ROOT / 'ATtiny88/Music/variants'
MICRONUCLEUS_OUTPUT = ROOT / 'ATtiny88/Music/variants-micronucleus'
VARIANTS = ('rhythmic', 'lumiere-stereo', 'alicia', 'children', 'turkish-march',
            'greensleeves', 'cancion-del-mariachi',
            'cancion-del-mariachi-polyphonic', 'cancion-del-mariachi-sparse')
CPU_HZ = 8_000_000
SYNTHESIS_HZ = CPU_HZ / 512
SOURCE_SYNTHESIS_HZ = 18_750
RAM_OFFSET = 0x100
BOARDS = {
    'bare-8mhz': dict(cpuHz=CPU_HZ, synthesisHz=SYNTHESIS_HZ,
                     virtualSamples=6, physicalSamples=5, flashLimit=8192),
    # This manufacturer's board clocks ATtiny88 above its ordinary 12 MHz
    # rating. Keep the board-specific configuration separate from bare chips.
    'mh-et-live-16mhz': dict(cpuHz=16_000_000, synthesisHz=31_250,
                           virtualSamples=3, physicalSamples=5, flashLimit=6012),
}
MANUFACTURER_BOARD_COMMIT = 'ee3207500e0a58ef3e6594ecaec2c846c21577f8'
MANUFACTURER_BOARD_URL = ('https://github.com/MHEtLive/MHEtLiveArduino/blob/'
                          +MANUFACTURER_BOARD_COMMIT+'/mhetlive-avr-1.0.0/1.0.0/boards.txt')


def run(command, *args, cwd=ROOT):
    result = subprocess.run([str(command), *map(str, args)], cwd=cwd,
                            capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f'{command}: {result.stderr or result.stdout}')
    return result.stdout


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8', newline='\n')


def ihex(raw):
    rows = []
    for start in range(0, len(raw), 16):
        payload = bytes([len(raw[start:start+16]), start >> 8, start & 255, 0]) + raw[start:start+16]
        rows.append(':' + (payload + bytes([-sum(payload) & 255])).hex().upper())
    return '\n'.join(rows + [':00000001FF', ''])


def toolchain(explicit):
    if explicit:
        folder = Path(explicit).resolve()
    elif shutil.which('avr-gcc'):
        folder = Path(shutil.which('avr-gcc')).parent
    else:
        # A task worktree shares the root checkout's downloaded toolchain.
        common = Path(run('git', 'rev-parse', '--git-common-dir').strip())
        if not common.is_absolute():
            common = ROOT / common
        candidates = [ROOT / 'build/toolchains/avr-7.3.0/bin',
                      common.resolve().parent / 'build/toolchains/avr-7.3.0/bin']
        folder = next((p for p in candidates if (p/'avr-gcc.exe').is_file()), candidates[0])
    suffix = '.exe' if os.name == 'nt' else ''
    tools = {name: folder / (name + suffix) for name in
             ('avr-gcc', 'avr-objcopy', 'avr-nm', 'avr-objdump')}
    for executable in tools.values():
        if not executable.is_file():
            raise FileNotFoundError(f'{executable}: install GNU AVR or pass --avr-bin')
    return tools


def expand(path):
    # The stereo source names registers from the retained official 13A map.
    # Normalize its instruction operands before targeting another device;
    # otherwise those 13A symbols conflict with the 88's C-preprocessor map.
    if path.name == 'attiny13a-registers.generated.inc':
        return ''
    text = path.read_text(encoding='utf-8')
    return re.sub(r'^\.include "([^"]+)"\s*$',
                  lambda m: expand(path.parent / m[1]).rstrip(), text, flags=re.M)


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f'Unexpected source layout ({text.count(old)} occurrences): {old!r}')
    return text.replace(old, new, 1)


def retuned(word, synthesis_hz=SYNTHESIS_HZ):
    flags, step = word & 0x8000, word & 0x7fff
    if not step:
        return word, None
    midi = round(69 + 12 * math.log2(step * SOURCE_SYNTHESIS_HZ / 65536 / 440))
    frequency = 440 * 2 ** ((midi - 69) / 12)
    # The retained words must represent equal-tempered notes, not arbitrary FX.
    assert abs(step - round(frequency * 65536 / SOURCE_SYNTHESIS_HZ)) <= 1, (word, midi)
    target = round(frequency * 65536 / synthesis_hz)
    assert 0 < target < 0x8000
    return target | flags, midi


def frequency_tables(source, rom, original, eeprom, sparse=False,
                     synthesis_hz=SYNTHESIS_HZ):
    patches = []
    labels = original['labels']
    for name in ('note_steps', 'chord_steps', 'pitch_steps', 'song_shapes'):
        if name not in labels or (sparse and name == 'song_shapes'):
            continue
        start = labels[name]
        end = min([v for v in labels.values() if v > start] + [len(rom)])
        raw = rom[start:end]
        assert len(raw) % 2 == 0, (name, len(raw))
        new = bytearray()
        for offset in range(0, len(raw), 2):
            old = int.from_bytes(raw[offset:offset+2], 'little')
            word, midi = retuned(old, synthesis_hz)
            new.extend(word.to_bytes(2, 'little'))
            patches.append(dict(space='flash', table=name, offset=offset,
                                sourceAddress=start+offset, sourceWord=old,
                                targetWord=word, midi=midi))
        pattern = rf'(^\s*{name}:\n).*?(?=^[A-Za-z_][\w.]*:\s*$|\Z)'
        lines = ''.join('  .byte ' + ', '.join(f'0x{x:02x}' for x in new[i:i+2]) + '\n'
                        for i in range(0, len(new), 2))
        source, count = re.subn(pattern, lambda m: m[1]+lines, source, count=1, flags=re.M | re.S)
        assert count == 1, name
    return source, bytearray(eeprom), patches


def relax_branches(source):
    """Expand only out-of-range AVR 7-bit branches, before GNU validation."""
    inverse = {'breq': 'brne', 'brne': 'breq', 'brcs': 'brcc', 'brcc': 'brcs',
               'brtc': 'brts', 'brts': 'brtc'}
    for serial in range(100):
        stripped = re.sub(r'/\*.*?\*/', '', source, flags=re.S)
        labels, rows, pc = {}, [], 0
        for line in stripped.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.endswith(':'):
                labels[line[:-1]] = pc
            elif line.startswith('.byte '):
                pc += len(line[6:].split(','))
            elif line.startswith('.balign '):
                alignment = int(line.split()[1])
                pc = (pc+alignment-1)//alignment*alignment
            elif line.startswith('.'):
                continue
            else:
                op = line.split()[0]
                rows.append((pc, line))
                pc += 4 if op in ('lds', 'sts') else 2
        change = next(((line, op, target) for at, line in rows
                       for op, target in [line.split() if len(line.split()) == 2 else ('', '')]
                       if op in inverse and not -64 <= (labels[target]-at-2)//2 <= 63), None)
        if change is None:
            return source
        line, op, target = change
        label = f'tiny88_long_branch_{serial}'
        source = source.replace('  '+line+'\n',
                                f'  {inverse[op]} {label}\n  rjmp {target}\n{label}:\n', 1)
    raise ValueError('Too many relaxed branches')


def port(source, name, board='bare-8mhz'):
    usb = board == 'mh-et-live-16mhz'
    stereo = name == 'lumiere-stereo'
    register_map = ROOT/'web-player/native/attiny13a-registers.generated.inc'
    registers = {key:int(value,0) for key,value in re.findall(
        r'^\.set (\w+),(0x[\da-fA-F]+|\d+)$',register_map.read_text(encoding='utf-8'),re.M)}
    source = re.sub(r'(^\s*(?:out|sbi)\s+)([A-Z][\w]*)(,)',
                    lambda m:m[1]+str(registers[m[2]])+m[3],source,flags=re.M)
    source = re.sub(r'(^\s*in r\d+, )([A-Z][\w]*)\b',
                    lambda m:m[1]+str(registers[m[2]]),source,flags=re.M)
    # Relocate original direct SRAM accesses before adding peripheral STS.
    source = re.sub(r'(\blds r\d+, )(\d+)', lambda m: m[1]+str(int(m[2])+RAM_OFFSET), source)
    source = re.sub(r'(\bsts )(\d+)(, r\d+)',
                    lambda m: m[1]+str(int(m[2])+RAM_OFFSET)+m[3], source)
    # Existing small images use otherwise-unused vector words as helpers.
    source = replace_once(source, '  rjmp pwm_irq\n', '')
    vectors = ''.join('  rjmp '+('reset' if i == 0 else 'pwm_irq' if i == 11 else 'unused_irq')+'\n'
                      for i in range(20))
    source = replace_once(source, 'vectors:\n  rjmp reset\n',
                          'vectors:\n'+vectors+'unused_irq:\n  rjmp reset\n')
    prefix = '''  /* ATtiny88: explicit stack, watchdog and 8 MHz prescaler setup. */
  cli
  wdr
  ldi r16, 2
  out 62, r16
  ldi r16, 255
  out 61, r16
  clr r17
  out 52, r17
  lds r16, 96
  ori r16, 24
  sts 96, r16
  sts 96, r17
  ldi r16, 128
  sts 97, r16
  sts 97, r17
  sts 100, r17
  ldi r16, 4
  out 42, r16
  ldi r16, 1
  out 43, r16
'''
    source = replace_once(source, 'reset:\n', 'reset:\n'+prefix)
    if usb:
        # USB entry is a jump from the bootloader, not necessarily a hardware
        # reset. Disable inherited interrupt sources before enabling Timer1.
        # These new board-only definitions come from avr-libc's vendor header;
        # the existing bare-8mhz source and binary remain unchanged.
        inherited = '''  /* Clear interrupt sources left by the USB bootloader. */
  out _SFR_IO_ADDR(EIMSK), r17
  sts _SFR_MEM_ADDR(PCICR), r17
  sts _SFR_MEM_ADDR(TIMSK0), r17
  out _SFR_IO_ADDR(TCCR0A), r17
  sts _SFR_MEM_ADDR(ADCSRA), r17
  out _SFR_IO_ADDR(ACSR), r17
'''
        source = replace_once(source, '  sts 100, r17\n', '  sts 100, r17\n'+inherited)
        source = source.replace('watchdog and 8 MHz prescaler setup.',
                                'watchdog and board clock prescaler setup.')
    source = re.sub(r'\s*/\* Requiredfuses7A/FF:.*?\*/', '', source)
    source = source.replace('  clr r27\n', '  ldi r27, 1\n')
    source = source.replace('  clr r31\n', '  ldi r31, 1\n')
    if name == 'cancion-del-mariachi-sparse':
        source = replace_once(source, '  ldi r26, 0\nclear_registers:',
                              '  clr r27\n  ldi r26, 0\nclear_registers:')
        source = replace_once(source, '  brne clear_registers\n', '  brne clear_registers\n  ldi r27, 1\n')
    # Main code relies on r29==0 for arithmetic; IRQ loads YH only temporarily.
    source = replace_once(source, 'ring_read:\n  ld r18, Y+\n',
                          'ring_read:\n  ldi r29, 1\n  ld r18, Y+\n')
    after = '  ld r8, Y+\n' if stereo else '  ld r18, Y+\n'
    source = replace_once(source, after, after+'  ldi r29, 0\n')
    # EEPROM address/control/data. Sparse's former spareOCR becomes GPIOR0.
    source = re.sub(r'\bout 30,', 'out 33,', source)
    source = source.replace('sbi 28, 0', 'sbi 31, 0')
    source = re.sub(r'(\bin r\d+, )29\b', r'\g<1>32', source)
    if not stereo:
        source = re.sub(r'\bout 54,', 'out 30,', source)
        source = re.sub(r'(\bin r\d+, )54\b', r'\g<1>30', source)
    # Use native ATtiny88 Timer1, not the non-PWM Timer0.
    # The original OC registers/COM now precede DDR, per both datasheets.
    start = source.index('  out 54, r18\n' if stereo else '  out 41, r18\n')
    end = source.index('  sei\n', start)+len('  sei\n')
    setup = '''  /* Fast PWM mode5, TOP255; high-byte TEMP remains zero. */
  clr r16
  sts 129, r16
  sts 111, r16
  sts 133, r16
  sts 132, r16
  sts 137, r16
  sts 139, r16
  sts 136, r18
  sts 138, r18
'''
    setup += f'''  ldi r16, {161 if stereo else 33}
  sts 128, r16
  /* Configure OC1x before enabling the pin driver (doc8008, section 12.7.3). */
  sbi 4, 2
'''
    if stereo:
        setup += '  sbi 4, 1\n'
    setup += '''
  ldi r16, 1
  out 22, r16
  sts 111, r16
  ldi r16, 9
  sts 129, r16
  sei
'''
    source = source[:start]+setup+source[end:]
    source = re.sub(r'\bout 41,', 'sts 138,', source)
    # Only source stereo output remains, GPIOR1 accesses use different regs.
    source = source.replace('  out 54, r18\n', '  sts 136, r18\n')
    # Everyfive physicalsamples advance six virtualsamples. ADDcarry catches
    # both255->0 and255->1; all envelopes/tempo/arps retain their old cadence.
    match = re.search(r'audio_step:\n  inc (r\d+)\n  brne render_sample\n', source)
    assert match, name
    timer = match[1]
    clock = f'''audio_step:
  in r16, 42
  subi r16, 1
  ldi r17, 1
  brcc tiny88_fraction_ready
  ldi r16, 4
  ldi r17, 2
tiny88_fraction_ready:
  out 42, r16
  out 43, r17
  add {timer}, r17
  brcc render_sample
'''
    if usb:
        # Countdown 4,1,3,0,2,4... advances 0,1,0,1,1 virtual samples.
        # ADD, rather than INC/Z, distinguishes a zero advance at phase 255
        # from a real 255 -> 0 rollover and retains the original 73.24 Hz tick.
        clock = f'''audio_step:
  in r16, 42
  subi r16, 3
  ldi r17, 0
  brcc tiny88_fraction_ready
  subi r16, 251
  ldi r17, 1
tiny88_fraction_ready:
  out 42, r16
  out 43, r17
  add {timer}, r17
  brcc render_sample
'''
    source = source[:match.start()]+clock+source[match.end():]
    if usb and name == 'turkish-march':
        # The original image could identify rests from the high DDS byte:
        # every sounding step was >=256. Retuning at 31,250 Hz also produces
        # sounding steps below256 (for example244), so test both bytes.
        # r17 is caller-clobbered at all initialize_voice call sites.
        source = replace_once(source,
            '  lpm r16, Z+\n  st X+, r16\n  lpm r16, Z+\n  st X+, r16\nvoice_initialized:\n'
            '  /* All selected nonzero DDS words are >=256. */\n  tst r16\n',
            '  lpm r16, Z+\n  st X+, r16\n  mov r17, r16\n  lpm r16, Z+\n  st X+, r16\nvoice_initialized:\n'
            '  /* Sounding retuned DDS steps may be smaller than256. */\n  or r16, r17\n')
    # Keep procedural drum oscillator clocks in physical seconds too.
    source = source.replace('  ldi r17, 1\n  add r14, r17\n', '  in r17, 43\n  add r14, r17\n')
    if 'render_kick:\n  inc r22\n' in source:
        source = source.replace('render_kick:\n  inc r22\n',
                                'render_kick:\n  in r25, 43\n  add r22, r25\n')
    # Retain low/high wave selection at its original physical boundary.
    low = 'r0' if name == 'alicia' else 'r24' if name == 'cancion-del-mariachi-sparse' else 'r6'
    high = 'r16' if 'render_tone:' in source else 'r25'
    old = f'  cpi {high}, 4\n'
    assert source.count(old) == 1, (name, source.count(old))
    threshold = round(1024 * SOURCE_SYNTHESIS_HZ / BOARDS[board]['synthesisHz'])
    decision = f'''  cpi {high}, {threshold >> 8}
  brne tiny88_register_decided
  mov {high}, {low}
  cpi {high}, {threshold & 255}
tiny88_register_decided:
'''
    if name == 'alicia':
        # r0 still holds the DDS lowbyte on entry; the envelope prologue then
        # reuses it. ANDI and BREQ preserve the carry from this comparison.
        source = source.replace(old, '', 1)
        source = replace_once(source, 'render_tone:\n', 'render_tone:\n'+decision)
    else:
        source = source.replace(old, decision, 1)
    # OriginalAli/Children layouts omitted some carryADCs using page proofs.
    # Extra targetsetup moves those tables: restore fullflashaddressaddition.
    source = re.sub(r'(  add r30, r\d+\n)(?!  adc r31,)', r'\1  adc r31, r29\n', source)
    source += '\nmusic_data_end:\n'
    if name in ('alicia', 'children', 'lumiere-stereo'):
        # These busy variants used a bit-serial multiply to fit1KB. The
        # new MCU can trade256Flash bytes for a much shorter exact operation.
        ending = r'  rjmp envelope_return\n' if stereo else r'  asr r17\n  asr r17\n  ret\n'
        pattern = r'  andi r17, 15\n  subi r17, 8\n\.L25c:\n.*?'+ending
        scratch = 12 if stereo else 10
        replacement = f'''  andi r17, 15
.L25c:
  movw r{scratch}, r30
  swap r25
  or r25, r17
  mov r30, r25
  ldi r31, hi8(amplitude_gain)
  lpm r17, Z
  movw r30, r{scratch}
  ret
'''
        source, count = re.subn(pattern, replacement, source, count=1, flags=re.S)
        assert count == 1, name
        gain = [((sample-8)*(level//2)//2 if stereo else (sample-8)*level//4) & 255
                for level in range(16) for sample in range(16)]
        source += '.balign 256\namplitude_gain:\n'
        source += ''.join('  .byte '+','.join(map(str,gain[i:i+16]))+'\n' for i in range(0,256,16))
    if name == 'cancion-del-mariachi-polyphonic':
        # The8oscillator version needs a shorter groupgain at the newrate.
        # qsum=-64..63, level=0..15; two levels share each256byte Flashpage.
        lookup = '''chord_gain:
  mov r16, r25
  movw r24, r30
  mov r31, r16
  lsr r31
  clr r30
  ror r30
  subi r21, 192
  add r30, r21
  ldi r16, hi8(chord_amplitude_gain)
  add r31, r16
  lpm r17, Z
  movw r30, r24
  ret
'''
        source, count = re.subn(r'chord_gain:\n.*?(?=music_tick:)', lookup, source, count=1, flags=re.S)
        assert count == 1
        gain = [(sample*level//8)&255 for level in range(16) for sample in range(-64,64)]
        source += '.balign 256\nchord_amplitude_gain:\n'
        source += ''.join('  .byte '+','.join(map(str,gain[i:i+16]))+'\n' for i in range(0,2048,16))
    return relax_branches(source)


def flash_wave_bank(source, name, bank):
    """Move the hardware read operation to Flash, retaining flags and live Z.

    The wavetable render call sites have a caller-clobbered register pair:
    r24:r25 after octave selection in the two compact engines, r12:r13 in
    stereo/Greensleeves, and r10:r11 in the remaining render_tone functions.
    A sparse control-time pitch read still has live codec state in those
    registers and therefore saves both Z bytes on the real SRAM stack.
    MOVW, MOV, LDI, LPM, PUSH and POP do not alter the arithmetic flags; in
    particular C retains the packed-waveform nibble selector from LSR.
    """
    reads = []
    pattern = r'  out 33, (r\d+)\n  sbi 31, 0\n  in (r\d+), 32\n'
    def replace(match):
        address, result = match.groups()
        label = f'tiny88_flash_read_{len(reads)}'
        control = name == 'cancion-del-mariachi-sparse' and result == 'r7'
        scratch = None if control else (24 if name.endswith(('-polyphonic','-sparse'))
                                       else 12 if name in ('lumiere-stereo','greensleeves') else 10)
        save_z = '  push r30\n  push r31\n' if control else f'  movw r{scratch}, r30\n'
        restore_z = '  pop r31\n  pop r30\n' if control else f'  movw r30, r{scratch}\n'
        reads.append(dict(label=label, inputRegister=int(address[1:]),
                          outputRegister=int(result[1:]), savedZ='stack' if control else f'r{scratch}:r{scratch+1}',
                          cycles=13 if control else 7, preservesSreg=True))
        return (save_z+f'  mov r30, {address}\n  ldi r31, hi8(embedded_wave_bank)\n'
                +label+f':\n  lpm {result}, Z\n'+restore_z)
    source, count = re.subn(pattern, replace, source)
    assert count == (3 if name == 'cancion-del-mariachi-sparse' else 1), (name,count)
    assert not re.search(r'\bsbi 31, 0|\bout 33,|\bin r\d+, 32\b', source)
    source += '\n.balign 256\nembedded_wave_bank:\n'
    source += ''.join('  .byte '+','.join(map(str,bank[i:i+16]))+'\n' for i in range(0,64,16))
    return source, reads


def build(name, tools, board='bare-8mhz'):
    config = BOARDS[board]
    usb = board == 'mh-et-live-16mhz'
    folder = SOURCE/name
    original = json.loads((folder/'build-report.json').read_text(encoding='utf-8'))
    rom = (folder/'synth.bin').read_bytes()
    ep = (folder/'eeprom.bin').read_bytes()
    assert sha(rom) == original['flashSha256']
    assert sha(ep) == original['eepromSha256']
    source = expand(folder/'synth.S')
    # Sparse shapes are addresses, while all other shape tables hold DDS words.
    sparse = name == 'cancion-del-mariachi-sparse'
    source, new_ep, patches = frequency_tables(source, rom, original, ep, sparse=sparse,
                                              synthesis_hz=config['synthesisHz'])
    if sparse:
        for address in range(32, 62, 2):
            old = int.from_bytes(ep[address:address+2], 'little')
            word, midi = retuned(old, config['synthesisHz'])
            new_ep[address:address+2] = word.to_bytes(2, 'little')
            patches.append(dict(space='eeprom', table='pitchPalette', offset=address-32,
                                sourceAddress=address, targetAddress=address,
                                sourceWord=old, targetWord=word, midi=midi))
    source = port(source, name, board=board)
    bank_reads = []
    if usb:
        source, bank_reads = flash_wave_bank(source, name, new_ep)
        source = '#include <avr/io.h>\n'+relax_branches(source)
    destination = (MICRONUCLEUS_OUTPUT if usb else OUTPUT)/name
    save(destination/'synth.S', '/* Generated by tools/build-attiny88-music.py. */\n'+source)
    scratch = ROOT/('build/attiny88-micronucleus' if usb else 'build/attiny88')/name
    scratch.mkdir(parents=True, exist_ok=True)
    elf = scratch/'synth.elf'
    run(tools['avr-gcc'], '-mmcu=attiny88', '-nostdlib', '-x', 'assembler-with-cpp' if usb else 'assembler',
        '-Wl,-e,vectors', '-Wl,--section-start=.text=0', destination/'synth.S', '-o', elf)
    binary = scratch/'synth.bin'
    run(tools['avr-objcopy'], '-O', 'binary', '-j', '.text', elf, binary)
    new_rom = binary.read_bytes()
    assert len(new_rom) <= config['flashLimit'], (name,len(new_rom),config['flashLimit'])
    symbols = run(tools['avr-nm'], '-n', elf)
    labels = {m[3]: int(m[1], 16) for m in re.finditer(r'^([0-9a-fA-F]+)\s+([tTaA])\s+(\S+)$', symbols, re.M)}
    for entry in patches:
        if entry['space'] == 'flash':
            entry['targetAddress'] = labels[entry['table']]+entry['offset']
            assert int.from_bytes(new_rom[entry['targetAddress']:entry['targetAddress']+2], 'little') == entry['targetWord']
        elif usb:
            entry['targetSpace'] = 'flash'
            entry['targetAddress'] = labels['embedded_wave_bank']+entry['offset']+32
            assert int.from_bytes(new_rom[entry['targetAddress']:entry['targetAddress']+2], 'little') == entry['targetWord']
    # Verify all retained data except explicitly regenerated frequency words.
    first = 'part_levels' if name == 'greensleeves' else 'song_shapes' if 'song_shapes' in labels else 'playlist'
    content_size = labels['music_data_end']-labels[first]
    old_data = bytearray(rom[original['labels'][first]:original['labels'][first]+content_size])
    new_data = bytearray(new_rom[labels[first]:labels['music_data_end']])
    for item in patches:
        if item['space'] == 'flash':
            at = item['sourceAddress']-original['labels'][first]
            new_data[at:at+2] = item['sourceWord'].to_bytes(2, 'little')
    assert old_data == new_data, (name, 'musical data changed beyond DDS retuning')
    for file, raw in [('synth.bin', new_rom)]+([] if usb else [('eeprom.bin', new_ep)]):
        (destination/file).write_bytes(raw)
        save(destination/file.replace('.bin', '.hex'), ihex(raw))
    if usb:
        (destination/'wave-bank.bin').write_bytes(new_ep)
    if name in ('cancion-del-mariachi-polyphonic', 'cancion-del-mariachi-sparse'):
        old_voices = list(range(112, 144 if not sparse else 136, 4))
        width, frequency_offset, envelope_offset = 4, 2, None
    elif name == 'greensleeves':
        old_voices, width, frequency_offset, envelope_offset = [112,117,122,127], 5, 3, 0
    elif name in ('alicia', 'children'):
        old_voices, width, frequency_offset, envelope_offset = [97,102,107,112,117,122], 5, 3, 0
    else:
        old_voices, width, frequency_offset, envelope_offset = [96,101,106,111,116], 5, 3, 0
        if name == 'turkish-march':
            old_voices = old_voices[:3]
    report = dict(target='ATtiny88', sourceVariant=name, engine=original.get('engine'),
                  sourceFolder=str(folder.relative_to(ROOT)).replace('\\','/'),
                  sourceFlashSha256=sha(rom), sourceEepromSha256=sha(ep),
                  sourceInputs={str(p.relative_to(ROOT)).replace('\\','/'):sha(p.read_bytes())
                                for p in sorted(folder.iterdir())
                                if p.name in ('synth.S','config.inc','score.inc','score.json','compiled-score.json','build-report.json')},
                  cpuHz=config['cpuHz'], pwmHz=config['cpuHz']/256, synthesisHz=config['synthesisHz'],
                  controlTickHz=SOURCE_SYNTHESIS_HZ/256,
                  controlClock=dict(virtualSamples=config['virtualSamples'], physicalSamples=5, divider=256,
                                    gpioCounter='GPIOR1', gpioAdvance='GPIOR2'),
                  audioChannels=2 if name == 'lumiere-stereo' else 1,
                  flashBytes=len(new_rom), codeBytes=labels[first], tableBytes=len(new_rom)-labels[first],
                  eepromBytes=0 if usb else 64, flashSha256=sha(new_rom), eepromSha256=None if usb else sha(new_ep), labels=labels,
                  requiredFuses=None if usb else dict(low='0xEE', high='0xDF', extended='0xFF'),
                  memory=dict(flashCapacity=8192, eepromCapacity=64, sramStart=256, sramEnd=767,
                              sourceVoiceAddresses=old_voices,
                              voiceAddresses=[a+RAM_OFFSET for a in old_voices],
                              voiceBytes=width, frequencyOffset=frequency_offset,
                              envelopeOffset=envelope_offset, relocationOffset=RAM_OFFSET,
                              sourceRingBase=96 if first != 'playlist' else 128,
                              ringBase=(96 if first != 'playlist' else 128)+RAM_OFFSET,
                              ringBytes=16),
                  hardware=dict(timer='Timer1', mode=5, top=255, overflowVector=11,
                                monoPin='PB2/OC1B', stereoLeftPin='PB1/OC1A', stereoRightPin='PB2/OC1B',
                                ocrHighByteInvariant=0, isrPreservesSreg=True),
                  frequencyPatches=patches, musicalDataVerified=True,
                  sourceToolchain='GNU AVR', toolchainVersion=run(tools['avr-gcc'],'--version').splitlines()[0])
    if usb:
        bank_address = labels['embedded_wave_bank']
        assert bank_address % 256 == 0
        assert new_rom[bank_address:bank_address+64] == new_ep
        header = tools['avr-gcc'].parent.parent/'avr/include/avr/iotn88.h'
        register_map = ROOT/'web-player/native/attiny13a-registers.generated.inc'
        report.update(board=board, applicationFlashLimit=config['flashLimit'],
                      storedFlashBytes=64, uploadProtocol='micronucleus',
                      boardClockAboveRatedMaximum=True,
                      boardSource=dict(version='1.0.0',commit=MANUFACTURER_BOARD_COMMIT,url=MANUFACTURER_BOARD_URL),
                      deviceHeader=dict(name='avr/iotn88.h',sha256=sha(header.read_bytes()),
                                        copyright='Atmel Corporation 2007',
                                        revision='$Id: iotn88.h 2225 2011-03-02 16:27:26Z arcanum $'),
                      wavetableHighStepThreshold=round(1024*SOURCE_SYNTHESIS_HZ/config['synthesisHz']),
                      wavetableStorage=dict(space='flash', address=bank_address,bytes=64,
                                            alignment=256,sha256=sha(new_ep)),
                      flashBankReads=bank_reads)
        report['sourceInputs'][str(register_map.relative_to(ROOT)).replace('\\','/')] = sha(register_map.read_bytes())
        report['generator'] = dict(path='tools/build-attiny88-music.py',
                                   sha256=sha(Path(__file__).read_text(encoding='utf-8').encode('utf-8')),
                                   sourceEncoding='UTF-8 with LF newlines')
        for read in bank_reads:
            read['address'] = labels[read['label']]
    if 'amplitude_gain' in labels:
        address = labels['amplitude_gain']
        stereo = name == 'lumiere-stereo'
        expected = bytes(((sample-8)*(level//2)//2 if stereo else (sample-8)*level//4)&255
                         for level in range(16) for sample in range(16))
        assert address % 256 == 0
        assert new_rom[address:address+256] == expected
        report['amplitudeGain'] = dict(address=address, bytes=256,
                                       formula='floor((sampleNibble - 8) * floor(level / 2) / 2)' if stereo
                                       else 'floor((sampleNibble - 8) * level / 4)',
                                       scratchRegisters=[12,13] if stereo else [10,11], verifiedInputs=256)
    if 'chord_amplitude_gain' in labels:
        address = labels['chord_amplitude_gain']
        expected = bytes((sample*level//8)&255 for level in range(16) for sample in range(-64,64))
        assert address % 256 == 0
        assert new_rom[address:address+2048] == expected
        report['chordGain'] = dict(address=address, bytes=2048, sumMinimum=-64, sumMaximum=63,
                                   formula='floor(sum * level / 8)', verifiedInputs=2048)
    save(destination/'build-report.json', json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    save(scratch/'disassembly.txt', run(tools['avr-objdump'], '-d', elf))
    print(f'{name}: {len(new_rom)}/{config["flashLimit"]} Flash, '
          +('0 EEPROM (64-byte Flash bank)' if usb else '64/64 EEPROM')
          +f', {len(patches)} DDS words verified')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('variants', nargs='*', choices=VARIANTS)
    parser.add_argument('--avr-bin', help='Directory containing avr-gcc and GNU AVR binutils')
    parser.add_argument('--board', choices=tuple(BOARDS), default='bare-8mhz',
                        help='Bare ISP 8 MHz chip or MH-ET LIVE 16 MHz Micronucleus board')
    args = parser.parse_args()
    compiler = toolchain(args.avr_bin)
    for variant in args.variants or VARIANTS:
        build(variant, compiler, board=args.board)
