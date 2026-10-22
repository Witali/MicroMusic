#!/usr/bin/env python3
"""Create an official-MDB input script from MicroMusic Intel HEX.

No MPLAB execution occurs here; to run the official simulator, install MPLAB X.
Microchip MDB User's Guide DS50002102L: Device, Hwtool SIM, Program, Stepi, Print.
"""
import argparse
from pathlib import Path
import subprocess
import sys

POINTS=[1,2,3,4,5,8,12,24,50,100,256,1024,4096]
REGS=['PCL','WREG','STATUS','BSR','FSR0L','FSR0H','OSCCON','PIR1','PIE1','INTCON',
      'TMR2','PR2','T2CON','PWM3DCH','PWM3DCL','PWM3CON']

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--mdb',help='Path to Microchip mdb.sh (Linux) or mdb.bat (Windows). Optional.')
    p.add_argument('--out',default='mdb_check.txt',help='Where to save the command script')
    args=p.parse_args()
    root=Path(__file__).resolve().parent
    image=(root/'micromusic_with_config.hex').resolve()
    if not image.exists():raise SystemExit('Missing '+str(image))
    lines=['# PIC16F1503 MicroMusic: independent MPLAB X SIM run',
        'Device PIC16F1503', 'Hwtool SIM', f'Program "{image}"', 'Reset MCLR', 'Sleep 100',
        'Echo MPLAB_CHECKS_BEGIN']
    previous=0
    for n in POINTS:
        lines.extend([f'Stepi {n-previous}',f'Echo CHECKPOINT_{n}'])
        previous=n
        for r in REGS:lines.append('Print '+r)
        lines.append('Stopwatch')
    lines.extend(['Echo MPLAB_CHECKS_END','Quit'])
    cmd=root/args.out
    cmd.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('MDB commands:',cmd,'\nHEX:',image)
    if args.mdb:
        log=root/'mdb_official_output.log'
        print('Running official MDB:',args.mdb)
        with log.open('w',encoding='utf-8') as f:
            r=subprocess.run([str(Path(args.mdb).expanduser()),str(cmd)],cwd=root,stdout=f,stderr=subprocess.STDOUT)
        print('MDB exit:',r.returncode,'; log:',log)
        if r.returncode:raise SystemExit(r.returncode)
if __name__=='__main__':main()
