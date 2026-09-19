"""Make a blank KiCad board with the badge drawn on Dwgs.User as a tracing guide.

The guide (badge outline, tact-switch bodies and pads, LEDs) is in badge
coordinates, so anything drawn over it lines up with the badge reference sketch
that kicad2fs.py emits. Dwgs.User is ignored by the converter.

Usage:
  python tools/make_goose_template.py "Archive 2/badge.kicad_pcb" goose/goose.kicad_pcb [quarter_turns]
  quarter_turns = 1 puts the badge top on the left (landscape); pass the same value
  to kicad2fs.py as --ref-turns.
"""
import os
import sys

from kicad2fs import parse_sexpr, reference, rotate_pt

HEADER = '''(kicad_pcb
	(version 20241229)
	(generator "pcbnew")
	(generator_version "9.0")
	(general (thickness 1.6) (legacy_teardrops no))
	(paper "A3")
	(layers
		(0 "F.Cu" signal)
		(2 "B.Cu" signal)
		(5 "F.SilkS" user "F.Silkscreen")
		(7 "B.SilkS" user "B.Silkscreen")
		(1 "F.Mask" user)
		(3 "B.Mask" user)
		(17 "Dwgs.User" user "User.Drawings")
		(19 "Cmts.User" user "User.Comments")
		(25 "Edge.Cuts" user)
		(27 "Margin" user)
		(31 "F.CrtYd" user "F.Courtyard")
		(29 "B.CrtYd" user "B.Courtyard")
		(35 "F.Fab" user)
		(33 "B.Fab" user)
		(39 "User.1" user)
		(41 "User.2" user)
	)
	(setup (pad_to_mask_clearance 0))
	(net 0 "")
	(net 1 "PENALTY")
	(net 2 "GOAL_1")
	(net 3 "GOAL_2")
	(net 4 "GND")
'''

# pogo-pin vias on the badge D-pad pads: (x, y, net)
PINS = [(73.8, 123.4, 1), (67.0, 131.0, 2), (89.6, 131.0, 3), (83.5, 134.2, 4)]


def main(badge_path, out_path, turns=0):
    turns = int(turns)
    loops = reference(parse_sexpr(open(badge_path, encoding='utf8').read()), turns)
    parts = [HEADER]
    for loop in loops:
        pts = ' '.join(f'(xy {x:.3f} {y:.3f})' for x, y in loop[:-1])
        parts.append(f'\t(gr_poly (pts {pts}) (stroke (width 0.1) (type solid)) (fill no) (layer "Dwgs.User"))\n')
    for x, y, net in PINS:
        x, y = rotate_pt((x, y), turns)
        parts.append(f'\t(via (at {x:.3f} {y:.3f}) (size 3) (drill 1) (layers "F.Cu" "B.Cu") (net {net}))\n')
    parts.append(')\n')
    os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)
    open(out_path, 'w', encoding='utf8').write(''.join(parts))
    print(f'{out_path}: {len(loops)} guide shapes on Dwgs.User')


if __name__ == '__main__':
    main(*sys.argv[1:4])
