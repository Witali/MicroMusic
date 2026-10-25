"""Render retained simulator queue traces (requires NumPy and matplotlib)."""
from pathlib import Path
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

root = Path(__file__).resolve().parent
report = json.loads((root / 'avr-timing.json').read_text())
fig, axes = plt.subplots(2, 1, figsize=(9, 6), layout='constrained')
for key, case in report['cases'].items():
    trace = case['occupancy_trace']
    time = (np.asarray([v['cycle'] for v in trace]) - trace[0]['cycle']) / 16000000
    axes[0].plot(time, [v['queued'] for v in trace], label=key)
    axes[1].plot(time, [v['underruns'] for v in trace], label=key)
axes[0].set(xlim=(0, .6), ylim=(-5, 515), ylabel='Queued samples',
            title='LPX4 Q0 / ATmega328P / 16 MHz / Timer1 + PWM IRQ active')
axes[1].set(xlabel='Seconds since first PWM tick', ylabel='Cumulative underruns')
for axis in axes:
    axis.grid(alpha=.25)
    axis.legend()
fig.savefig(root / 'avr-queue.png', dpi=160)
