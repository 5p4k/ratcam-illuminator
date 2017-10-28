from __future__ import unicode_literals
from polar import *
from pcb import ToPCB, FromPCB
import math
import pcbnew

_OPTIONS = {
    'lines': 3,
    'leds_per_line': 3,
    'led_ref': lambda line_idx, led_idx: 'LED%d' % (line_idx * OPT('leds_per_line') + led_idx),
    'res_ref': lambda line_idx: 'R%d' % line_idx,
    'init_angle': 0.,
    'led_orient': 0.,
    'res_orient': math.pi,
    'radius': pcbnew.FromMM(30.),
    'lines_pad_on_circ': True
}


def OPT(k, default=None):
    global _OPTIONS
    return _OPTIONS.get(k, default)


def place_one_2comp(comp, angle, radius, orient=0.):
    if OPT('lines_pad_on_circ'):
        chord = Chord(radius, 0., angle).with_length(comp.get_two_pads_distance())
        comp.align_pads_to_chord(chord)
        comp.orientation += orient
    else:
        comp.orientation = orient + angle - math.pi / 2.
        comp.position = Polar(angle, radius).to_point()


def place_led_lines(board):
    n_comps = OPT('lines') * (OPT('leds_per_line') + 1)
    angle_step = 2. * math.pi / float(n_comps)
    angle = OPT('init_angle')
    for line_idx in range(OPT('lines')):
        place_one_2comp(board.components[OPT('res_ref')(line_idx)],
                        angle, OPT('radius'), OPT('res_orient'))
        angle += angle_step
        for led_idx in range(OPT('leds_per_line')):
            place_one_2comp(board.components[OPT('led_ref')(line_idx, led_idx)],
                            angle, OPT('radius'), OPT('led_orient'))
            angle += angle_step


def main():
    board = FromPCB.populate()
    place_led_lines(board)
    ToPCB.apply(board)


if __name__ == '__main__':
    main()
