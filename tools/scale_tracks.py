"""Scale every copper track in a .kicad_pcb about a point and set its width.

KiCad's PCB editor has no scale tool, so this edits the file directly. Only
(segment ...) tracks are touched; the Dwgs.User badge guide stays put.

Usage:
  python tools/scale_tracks.py in.kicad_pcb out.kicad_pcb --scale 2 --width 2.5
  (default centre is the badge D-pad centre, 78.4 129.0)
"""
import argparse
import re


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src')
    ap.add_argument('dst')
    ap.add_argument('--scale', type=float, required=True)
    ap.add_argument('--width', type=float, help='new track width in mm')
    ap.add_argument('--centre', nargs=2, type=float, default=[78.4, 129.0], metavar=('X', 'Y'))
    args = ap.parse_args()
    cx, cy = args.centre

    def point(m):
        x, y = float(m[2]), float(m[3])
        return f'({m[1]} {cx + (x - cx) * args.scale:.4f} {cy + (y - cy) * args.scale:.4f})'

    def segment(m):
        s = re.sub(r'\((start|end) (-?[\d.]+) (-?[\d.]+)\)', point, m[0])
        if args.width:
            s = re.sub(r'\(width [\d.]+\)', f'(width {args.width})', s)
        return s

    text = open(args.src, encoding='utf8').read()
    text, n = re.subn(r'\(segment\b.*?\(uuid "[^"]*"\)\s*\)', segment, text, flags=re.S)
    open(args.dst, 'w', encoding='utf8').write(text)
    print(f'{args.dst}: {n} tracks scaled x{args.scale}' + (f', width {args.width} mm' if args.width else ''))


if __name__ == '__main__':
    main()
