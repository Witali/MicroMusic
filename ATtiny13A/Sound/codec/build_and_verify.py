from pathlib import Path
import hashlib,subprocess,csv
root=Path(__file__).resolve().parent
with (root/'report.csv').open() as f: reports={r['phrase']:r for r in csv.DictReader(f)}
for name,report in reports.items():
  d=root/name
  subprocess.run(['clang','-target','avr','-mmcu=attiny13','-c','firmware.S','-o','firmware.o'],cwd=d,check=True)
  subprocess.run(['llvm-objcopy','-O','binary','firmware.o','recompiled.bin'],cwd=d,check=True)
  got=(d/'recompiled.bin').read_bytes();expected=(d/'firmware.bin').read_bytes()
  assert got==expected,(name,len(got),len(expected),'binary mismatch')
  assert hashlib.sha256(got).hexdigest()==report['flash_sha256']
  print(name,'OK',len(got),'bytes')
