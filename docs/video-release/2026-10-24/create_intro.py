"""Draw and encode a four-second title card matching the MicroMusic website."""
from pathlib import Path
import subprocess

from PIL import Image, ImageDraw, ImageFont

ROOT = Path('C:/Work/YouTube Videos/MicroMusic/materials/work')
ROOT.mkdir(parents=True, exist_ok=True)
image = Image.new('RGB', (1920, 1080), '#081611')
draw = ImageDraw.Draw(image)
for y in range(1080):
    draw.line((0, y, 1919, y), fill=(8, 22 + round(8 * y / 1080), 17 + round(5 * y / 1080)))
for x in range(40, 1920, 48):
    for y in range(36, 1080, 48):
        draw.ellipse((x, y, x+2, y+2), fill='#233b30')


def text(x, baseline, content, size, color, bold=False):
    font = ImageFont.truetype('C:/Windows/Fonts/' + ('segoeuib.ttf' if bold else 'segoeui.ttf'), size)
    draw.text((x, baseline), content, font=font, fill=color, anchor='ls')


lime = '#c4f68a'
cyan = '#75d7dc'
# SOP-8: four gull-wing leads on each side, no top or bottom leads.
for y in (345, 455, 565, 675):
    draw.rounded_rectangle((1230, y-22, 1328, y+22), radius=7, fill='#aebfba')
    draw.rectangle((1270, y-22, 1328, y+22), fill='#c5d2cb')
    draw.line((1238, y-15, 1318, y-15), fill='#ecf4e8', width=3)
    draw.rounded_rectangle((1762, y-22, 1860, y+22), radius=7, fill='#aebfba')
    draw.rectangle((1762, y-22, 1820, y+22), fill='#c5d2cb')
    draw.line((1772, y-15, 1852, y-15), fill='#ecf4e8', width=3)
draw.rounded_rectangle((1320, 285, 1770, 735), radius=21, fill='#10271e', outline='#75aa80', width=3)
draw.line((1340, 296, 1750, 296), fill='#42614e', width=3)
draw.ellipse((1350, 315, 1370, 335), fill=cyan)
text(1385, 440, 'ATtiny13A', 55, '#ecf4e8', True)
text(1392, 555, '1024', 100, lime, True)
text(1415, 625, 'байта Flash', 39, '#acc1b4')
text(1486, 696, 'SOP-8', 31, '#75aa80')
text(145, 250, 'ПАМЯТЬ ДОРОГАЯ?', 65, '#ecf4e8', True)
text(125, 590, '1 КБ', 340, lime, True)
text(145, 735, 'ХВАТИТ ВСЕМ!', 89, '#ecf4e8', True)
draw.line((150, 815, 1120, 815), fill='#38543e', width=2)
text(145, 910, 'MicroMusic', 58, cyan, True)
text(148, 973, 'Музыка и речь на маленьких чипах', 39, '#acc1b4')
image.save(ROOT / 'intro.png')
command = ['ffmpeg', '-y', '-hide_banner', '-nostats', '-loop', '1', '-i',
           str(ROOT / 'intro.png'), '-f', 'lavfi', '-i',
           'anullsrc=r=48000:cl=stereo', '-t', '4', '-vf',
           'fps=30,fade=t=in:st=0:d=0.3,fade=t=out:st=3.65:d=0.35,format=yuv420p',
           '-c:v', 'libx264', '-preset', 'fast', '-crf', '17', '-tune', 'stillimage',
           '-profile:v', 'high', '-level:v', '4.0', '-bf', '0', '-g', '60',
           '-video_track_timescale', '90000', '-color_range', 'tv',
           '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709',
           '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart', str(ROOT / 'intro.mp4')]
result = subprocess.run(command, capture_output=True)
(ROOT / 'intro-render.log').write_bytes(result.stderr)
result.check_returncode()
print(ROOT / 'intro.mp4')
