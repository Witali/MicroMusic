"""Build Cancion del Mariachi from retained guitar events, without MIDI binaries.

The requested edit skips the introduction and starts at source beat 58.
The selected passage contains only eighths and triplets: six grid units per
quarter preserve both exactly. The second source guitar takes over during
rests in the first. Rhythm guitar, bass and quiet drums support both parts.
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
FIRST_BEAT = 58
LAST_BEAT = 121
GRID_UNITS = 6
HARMONY = {
    'Em': dict(classes={4, 7, 11}, rhythm=[55, 59], bass=[40, 47]),
    'B7': dict(classes={11, 3, 6, 9}, rhythm=[51, 57], bass=[35, 42]),
    'Am': dict(classes={9, 0, 4}, rhythm=[60, 64], bass=[45, 40]),
}


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / filename)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def arrange(candidates=384):
    reader = module('mariachi_events', 'midi-events.py')
    compiler = module('mariachi_format', 'score-format.py')
    document = reader.load(SOURCE)
    notes, ppqn, bpm = reader.notes(document)
    assert bpm == 126 and ppqn == 480
    selected = [(i, n) for i, n in enumerate(notes)
                if n[3] < LAST_BEAT * ppqn and n[4] > FIRST_BEAT * ppqn]
    assert all(n[3] * GRID_UNITS % ppqn == n[4] * GRID_UNITS % ppqn == 0 for _, n in selected)
    quantized = [dict(identity=i, track=n[0], pitch=n[2],
                      start=round(n[3] * GRID_UNITS / ppqn) - FIRST_BEAT * GRID_UNITS,
                      end=round(n[4] * GRID_UNITS / ppqn) - FIRST_BEAT * GRID_UNITS)
                 for i, n in selected]
    stop = (LAST_BEAT - FIRST_BEAT) * GRID_UNITS
    grid = []
    controls = []
    chord_notes = {}
    previous_harmony = 'Em'
    harmony_events = []
    selected_lead = []
    for unit in range(stop):
        lead = [n for n in quantized if n['track'] == 0 and n['start'] <= unit < n['end']]
        guitar = [n for n in quantized if n['track'] == 1 and n['start'] <= unit < n['end']]
        active = lead or guitar
        chosen = max(active, key=lambda n:(n['pitch'], n['start'])) if active else None
        selected_lead.append(chosen)
        grid.append((compiler.pname(chosen['pitch']), chosen['identity']) if chosen else ('R', None))
        if unit % GRID_UNITS:
            continue
        # Infer the three familiar harmonies from full source voicings. Before
        # Gtr.2 enters, the melody's chord tones provide the same evidence.
        classes = {n['pitch'] % 12 for n in (guitar or lead)}
        ranked = [(len(classes & value['classes']) - 2 * len(classes - value['classes']),
                   name == previous_harmony, name) for name, value in HARMONY.items()]
        harmony = max(ranked)[2] if classes else previous_harmony
        quarter = unit // GRID_UNITS
        phase = quarter % 2
        if guitar:
            voicing = sorted({n['pitch'] for n in guitar})
            rhythm, bass = voicing[-2] if len(voicing)>1 else voicing[-1], voicing[0]
        else:
            rhythm, bass = HARMONY[harmony]['rhythm'][phase], HARMONY[harmony]['bass'][phase]
        name = f'guitar_{rhythm}_{bass}'
        chord_notes[name] = [rhythm, bass]
        controls.append(dict(unit=unit, chord=name))
        harmony_events.append(dict(unit=unit, harmony=harmony, phase=phase))
        previous_harmony = harmony
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
    controls.append(dict(unit=stop, offMask=14))
    played = {n['identity']: n for n in selected_lead if n is not None}
    longest_rest = current_rest = 0
    for n in selected_lead:
        current_rest = 0 if n is not None else current_rest + 1
        longest_rest = max(longest_rest, current_rest)
    coverage = dict(sourceSelectedAttacks={str(track):sum(n[0]==track for _,n in selected) for track in (0,1)},
                    leadSelectedAttacks={str(track):sum(n['track']==track for n in played.values()) for track in (0,1)},
                    longestMelodicRestSeconds=longest_rest/GRID_UNITS*60/bpm,
                    fullMidiPolyphonyPreserved=False,
                    policy='The first guitar has priority; the second supplies its real note attacks during first-guitar rests. Rhythm voicing and bass remain reduced.')
    return dict(title='Canción del Mariachi · Отчаянный', composers=['César Rosas'],
        player_description='ведущая и ритмическая нейлоновые гитары, бас и тихие ударные FluidR3; в паузах ведущей партии звучит перебор второй гитары.',
        performers=['Los Lobos', 'Antonio Banderas'], engine='instrument-bank',
        tempo_bpm=bpm * GRID_UNITS // 4, musicalTempoBpm=bpm, sourceMeters='4/4',
        beats_per_bar=4, release_tail_slots=2,
        percussion_half_beat_units=3,
        instruments=dict(lead=dict(instrument='acoustic-guitar-nylon', level=15),
                         keys=dict(instrument='acoustic-guitar-nylon', level=10),
                         pluck=dict(instrument='fretless-bass', level=8),
                         percussion=dict(instrument='natural-kit', level=2)),
        patterns=dict(song=bars, silence=['R:4']), playlist=['song', 'silence'],
        chord_pairs=[[first, first]], chord_notes=chord_notes,
        replace_harmony_sections=['song', 'silence'],
        timed_controls=dict(song=controls, silence=[dict(unit=0, offMask=14)]),
        arrangementHarmony=harmony_events,
        sourceNoteCoverage=coverage,
        packing_candidates=candidates, packing_max_entry_offset=255,
        source=dict(file='../../reference/cancion-del-mariachi/source-events.json',
                    sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                    originalMidiSha256=document['source']['sha256'], sourceQuarterBeats=314,
                    firstSourceQuarterBeat=FIRST_BEAT, lastSourceQuarterBeat=LAST_BEAT,
                    arrangedQuarterBeats=stop/GRID_UNITS, gridUnitsPerQuarter=GRID_UNITS, completeSource=False,
                    excerpt='Source beats 58..121; introduction omitted at the user\'s request. Main theme starts immediately; final source E4 cadence releases before the loop.',
                    reduction='Highest active source note in Gtr.1 Antonio, switching to the highest Gtr.2 Meysam source note during rests. Rhythm guitar samples the second-highest source Gtr.2 note once per quarter, and bass samples its lowest note; before Gtr.2 enters, Em/B7/Am accompaniment is arranged from source chord tones. Middle chord tones remain omitted. Quiet new kick/hat/snare/hat plays two hits per musical quarter.',
                    timing='Exact selected source ticks on a 1/6-quarter grid, encoded as sixteenths at 1.5x BPM. Source tempo 126 quarter BPM; drums use their own three-grid-unit countdown on this same grid.'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--candidates', type=int, default=384)
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
