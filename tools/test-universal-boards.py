"""Check retained UM88 USB upload boundaries and explicit board selection."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
FOLDER=ROOT/'ATtiny88/Music/universal/songs-micronucleus'

class Boards(unittest.TestCase):
    def test_flash_only_images_reset_vectors_and_factory_fuses(self):
        folders=sorted(p for p in FOLDER.iterdir() if p.is_dir() and (p/'build-report.json').exists())
        self.assertEqual(len(folders),9)
        engines={};counts={1:0,2:0}
        for folder in folders:
            with self.subTest(song=folder.name):
                meta=json.loads((folder/'build-report.json').read_text(encoding='utf-8'))
                raw=(folder/'synth.bin').read_bytes()
                self.assertEqual(meta['cpuHz'],16000000)
                self.assertEqual(meta['pwmHz'],62500)
                self.assertEqual(meta['synthesisHz'],15625)
                self.assertEqual(meta['applicationFlashLimit'],6012)
                self.assertLessEqual(len(raw),6012)
                self.assertEqual(hashlib.sha256(raw).hexdigest(),meta['flashSha256'])
                self.assertFalse(meta['eepromRequired'])
                self.assertEqual(meta['eepromBytes'],0)
                self.assertIsNone(meta['eepromSha256'])
                self.assertFalse((folder/'eeprom.bin').exists())
                self.assertFalse((folder/'eeprom.hex').exists())
                self.assertIsNone(meta['requiredFuses'])
                self.assertTrue(meta['preserveFactoryFuses'])
                self.assertEqual(meta['uploadProtocol'],'micronucleus')
                self.assertEqual(meta['configuredChannels'],meta['channels'])
                self.assertEqual(meta['renderABI'],'mono-s16' if meta['configuredChannels']==1 else 'packed-stereo-u32')
                counts[meta['configuredChannels']]+=1
                self.assertEqual(meta['pwmBufferFrames']*meta['channels'],meta['pwmBufferBytes'])
                self.assertEqual(meta['pwmBufferLayout'],'stereo-pairs' if meta['channels']==2 else 'mono')
                vector=int.from_bytes(raw[:2],'little')
                self.assertEqual(vector&0xf000,0xc000,'Micronucleus uploader needs RJMP reset')
                reset=vector&0xfff
                if reset&0x800:reset-=0x1000
                self.assertEqual((reset+1)*2,meta['resetVector']['target'])
                labels=meta['labels']
                self.assertLess(meta['resetVector']['target'],labels['um_board_reset'])
                self.assertLess(labels['um_board_reset'],labels['__do_clear_bss'])
                self.assertLess(labels['__do_clear_bss'],labels['main'])
                wave=meta['wavetableStorage']
                self.assertEqual(wave['space'],'flash')
                bank=raw[wave['address']:wave['address']+wave['bytes']]
                self.assertEqual(hashlib.sha256(bank).hexdigest(),wave['sha256'])
                self.assertEqual(bank,bytes(json.loads((folder/'score.json').read_text())['waves']))
                profile=(meta['configuredChannels'],meta['cpuHz'],meta['backend'],meta['packingMode'],meta['pwmBufferBytes'])
                code=hashlib.sha256(raw[:meta['engineBytes']]).hexdigest()
                self.assertEqual(engines.setdefault(profile,code),code,'Each configured profile uses one common engine')
        self.assertEqual(counts,{1:8,2:1})
        self.assertEqual(len(engines),2,'Mono and stereo are separately compiled profiles')

    def test_conflicting_board_cpu_rejected_before_compilation(self):
        result=subprocess.run([sys.executable,str(ROOT/'tools/build-universal-music.py'),
            '--board','mh-et-live-16mhz','--cpu-hz','8000000'],cwd=ROOT,capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('requires --cpu-hz 16000000',result.stderr)

    def test_quarter_ramp_preserves_all_nested_midpoint_rounding(self):
        for previous in range(256):
            for target in range(256):
                midpoint=(previous+target)//2
                expected=[(previous+midpoint)//2,midpoint,(midpoint+target)//2,target]
                ramp=[(previous*4+(target-previous)*n)//4 for n in range(1,5)]
                self.assertEqual(ramp,expected)

if __name__=='__main__':unittest.main()
