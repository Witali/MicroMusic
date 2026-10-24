"""Build Cancion del Mariachi from retained guitar events, without MIDI binaries.

The source contains straight eighths, triplets and finer ornaments. Twenty-four
grid units per real quarter preserve every source tick exactly. The existing
sixteenth decoder runs at 6x BPM. Four-quarter storage blocks do not change
musical meter. The explicit excerpt stops on the E4 cadence.
"""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import shutil

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'ATtiny13A/Music/reference/cancion-del-mariachi/source-events.json'
OUTPUT = ROOT / 'ATtiny13A/Music/variants/cancion-del-mariachi'


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / filename)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def arrange(candidates=192, grid_units=24):
    reader = module('mariachi_events', 'midi-events.py')
    compiler = module('mariachi_format', 'score-format.py')
    document = reader.load(SOURCE)
    notes, ppqn, bpm = reader.notes(document)
    assert bpm == 126 and ppqn == 480
    quantized = [dict(identity=i, track=n[0], pitch=n[2],
                      start=round(n[3] * grid_units / ppqn), end=round(n[4] * grid_units / ppqn))
                 for i, n in enumerate(notes)]
    assert all(n[3] * grid_units % ppqn == n[4] * grid_units % ppqn == 0 for n in notes)
    # Keep the complete source in JSON; explicitly arrange its opening through
    # the E4 cadence at source beat 121. The full three-part image exceeds 1 KB.
    stop = 121 * grid_units
    grid = []
    controls = []
    chord_notes = {}
    previous = None
    for unit in range(stop):
        lead = [n for n in quantized if n['track'] == 0 and n['start'] <= unit < n['end']]
        chosen = max(lead, key=lambda n:(n['pitch'], n['start'])) if lead else None
        grid.append((compiler.pname(chosen['pitch']), chosen['identity']) if chosen else ('R', None))
        guitar = [n for n in quantized if n['track'] == 1 and n['start'] <= unit < n['end']]
        # Sample one source strum per real quarter: thumb bass and upper voice.
        high = max(guitar, key=lambda n:(n['pitch'], n['start'])) if guitar else None
        low = min(guitar, key=lambda n:(n['pitch'], -n['start'])) if guitar else None
        signature = (high['identity'], low['identity']) if high else None
        if unit % grid_units != 0:continue
        if signature != previous:
            if high:
                name = f"guitar_{high['pitch']}_{low['pitch']}"
                chord_notes[name] = [high['pitch'], low['pitch']]
                controls.append(dict(unit=unit, chord=name))
            else:
                controls.append(dict(unit=unit, offMask=6))
        previous = signature
    first = next(c['chord'] for c in controls if 'chord' in c)
    # Pad storage only after the excerpt has finished; release all parts.
    size = (stop + 15) // 16 * 16
    grid.extend([('R', None)] * (size - len(grid)))
    bars = []
    for start in range(0, size, 16):
        tokens = []
        unit = start
        while unit < start + 16:
            end = unit + 1
            while end < start + 16 and grid[end] == grid[unit]:
                end += 1
            note = grid[unit][0]
            tied = end < size and grid[end] == grid[unit] and note != 'R'
            tokens.append(f"{note}:{(end - unit) / 4:g}" + ('~' if tied else ''))
            unit = end
        bars.append(' '.join(tokens))
    controls.append(dict(unit=stop, offMask=6))
    return dict(title='Canción del Mariachi · Отчаянный', composers=['César Rosas'],
        player_description='три партии нейлоновой гитары FluidR3 и два резервных канала затухания.',
        performers=['Los Lobos', 'Antonio Banderas'], engine='instrument-bank',
        tempo_bpm=bpm * grid_units // 4, musicalTempoBpm=bpm, sourceMeters='3/4, 4/4, 2/4',
        beats_per_bar=4, release_tail_slots=2,
        instruments=dict(lead=dict(instrument='acoustic-guitar-nylon', level=15),
                         keys=dict(instrument='acoustic-guitar-nylon', level=8),
                         pluck=dict(instrument='acoustic-guitar-nylon', level=10), percussion='off'),
        patterns=dict(song=bars, silence=['R:4']), playlist=['song', 'silence'],
        chord_pairs=[[first, first]], chord_notes=chord_notes,
        replace_harmony_sections=['song', 'silence'],
        timed_controls=dict(song=controls, silence=[dict(unit=0, offMask=6)]),
        packing_candidates=candidates, packing_max_entry_offset=255,
        source=dict(file='../../reference/cancion-del-mariachi/source-events.json',
                    sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                    originalMidiSha256=document['source']['sha256'], sourceQuarterBeats=314,
                    arrangedQuarterBeats=stop/grid_units, gridUnitsPerQuarter=grid_units, completeSource=False,
                    excerpt='Source beats 0..121, including the original introduction and its rests; E4 cadence then all voices release.',
                    reduction='Highest active source note in Gtr.1 Antonio; highest and lowest active Gtr.2 Meysam notes sampled once per source quarter. Middle chord tones and extra strums omitted; no generated drums. Companion NoteOffs are sampled at source quarter boundaries.',
                    timing='Exact source ticks, including eighths, triplets and fine ornaments, on a 1/24-quarter grid encoded as sixteenths at 6x BPM. Source tempo 126 quarter BPM.'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--candidates', type=int, default=192)
    args = parser.parse_args()
    builder = module('mariachi_builder', 'build-rhythmic.py')
    OUTPUT.mkdir(parents=True, exist_ok=True)
    builder.save_text(OUTPUT / 'score.json', json.dumps(arrange(args.candidates), ensure_ascii=False, indent=2) + '\n')
    for filename in ('avr_core.js', 'FluidR3-MIT.txt'):
        shutil.copyfile(ROOT / 'ATtiny13A/Music/variants/rhythmic' / filename, OUTPUT / filename)
    if not args.prepare_only:
        builder.build(OUTPUT)


if __name__ == '__main__':
    main()
