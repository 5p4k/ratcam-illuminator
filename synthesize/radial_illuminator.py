from __future__ import unicode_literals
from pcb import ToPCB, FromPCB
from cad import Component
import math
import pcbnew

# Thanks https://stackoverflow.com/a/23689767/1749822
class dotdict(dict):
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__


OPT = dotdict(
    lines=dotdict(
        n=3,
        leds=3,
        led_ref=lambda line_idx, led_idx: 'LED%d' % (line_idx * OPT.lines.leds + led_idx),
        res_ref=lambda line_idx: 'R%d' % line_idx,
        init_angle=0.,
        led_orient=0.,
        res_orient=math.pi,
        radius=pcbnew.FromMM(30.),
        pad_on_circ=True
    )
)


def get_lines(board, component_only):
    for line_idx in range(OPT.lines.n):
        comp = board.components[OPT.lines.res_ref(line_idx)]
        yield comp if component_only else (comp, False)
        for led_idx in range(OPT.lines.leds):
            comp = board.components[OPT.lines.led_ref(line_idx, led_idx)]
            yield comp if component_only else (comp, True)


def place_lines(board):
    n_comps = OPT.lines.n * (OPT.lines.leds + 1)
    angle_step = 2. * math.pi / float(n_comps)
    angle = OPT.lines.init_angle
    place = Component.place_pads_on_circ if OPT.lines.pad_on_circ else Component.place_radial
    for comp, is_led in get_lines(board, False):
        place(comp, angle, OPT.lines.radius, orientation=OPT.lines.led_orient if is_led else OPT.lines.res_orient)
        angle += angle_step


def route_led_lines(board):
    lines_comps = list(get_lines(board, True))
    for net in board.netlist.values():
        if len(net.terminals) != 2:
            continue
        if net.terminals[0].component not in lines_comps or net.terminals[1].component not in lines_comps:
            continue
        del net.tracks[:]
        net.route_arc()


def main():
    board = FromPCB.populate()
    place_lines(board)
    route_led_lines(board)
    ToPCB.apply(board)


if __name__ == '__main__':
    main()
