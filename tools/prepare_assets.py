"""Fetch reproducible self-hosted font and flag assets; not required at runtime."""
from pathlib import Path
from urllib.request import urlopen

from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1]
fonts = ROOT / 'static' / 'fonts'
fonts.mkdir(parents=True, exist_ok=True)
source = 'https://raw.githubusercontent.com/google/fonts/main/ofl/manrope/'
ttf = fonts / 'manrope.ttf'
ttf.write_bytes(urlopen(source + 'Manrope%5Bwght%5D.ttf', timeout=30).read())
font = TTFont(ttf)
font.flavor = 'woff2'
font.save(fonts / 'manrope.woff2')
ttf.unlink()
(fonts / 'OFL.txt').write_bytes(urlopen(source + 'OFL.txt', timeout=30).read())
flags = ROOT / 'static' / 'images' / 'flags'
flags.mkdir(parents=True, exist_ok=True)
for code in ('sa', 'ae', 'qa', 'kw', 'us', 'gb', 'tr', 'in', 'pk', 'bd'):
    (flags / (code + '.svg')).write_bytes(urlopen('https://flagcdn.com/' + code + '.svg', timeout=30).read())
print('Prepared Manrope WOFF2 with OFL license and 10 SVG flags.')
