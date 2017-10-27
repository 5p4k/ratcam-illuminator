from __future__ import unicode_literals
from polar import *
from pcb import ToPCB, FromPCB
import math
import pcbnew


ARRANGEMENT = (3, 3)
LED_REF = lambda line_idx, led_idx: 'LED%d' % (line_idx * ARRANGEMENT[0] + led_idx)
RES_REF = lambda line_idx: 'R%d' % line_idx
INITIAL_ANGLE = 0.
RADIUS = pcbnew.FromMM(30.)
PADS_ON_CIRCUMFERENCE = True


def place_one_2comp(comp, angle, radius):
    if PADS_ON_CIRCUMFERENCE:
        chord = Chord(radius, 0., angle).with_length(comp.get_two_pads_distance())
        comp.align_pads_to_chord(chord)
    else:
        comp.orientation = angle
        comp.position = Polar(angle, radius).to_point()


def place_led_lines(board):
    n_comps = ARRANGEMENT[0] * ARRANGEMENT[1]
    angle_step = 2. * math.pi / float(n_comps)
    angle = INITIAL_ANGLE
    for line_idx in range(ARRANGEMENT[0]):
        place_one_2comp(board.components[RES_REF(line_idx)], angle, RADIUS)
        angle += angle_step
        for led_idx in range(ARRANGEMENT[1]):
            place_one_2comp(board.components[LED_REF(line_idx, led_idx)], angle, RADIUS)
            angle += angle_step


def main():
    board = FromPCB.populate()
    place_led_lines(board)
    ToPCB.apply(board)


if __name__ == '__main__':
    main()
