from __future__ import unicode_literals, print_function
from pcb import ToPCB, FromPCB
from cad import Component, Track, Fill
from polar import Polar, apx_arc_through_polars, normalize_angle, Chord, apx_crown_sector
import math
import pcbnew
import sys

# Thanks https://stackoverflow.com/a/23689767/1749822
class dotdict(dict):
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__


OPT = dotdict(
    lines=dotdict(
        n_lines=3,
        n_leds=3,
        led_orient=math.pi,
        res_orient=0.,
        radius=pcbnew.FromMM(30.),
        pad_on_circ=True,
        led_pfx='LED',
        res_pfx='R'
    ),
    rings=dotdict(
        pwr_radius=pcbnew.FromMM(33.),
        gnd_radius=pcbnew.FromMM(27.)
    ),
    pours=dotdict(
        parallel_to_comp=False,
        inner_radius=pcbnew.FromMM(28.),
        outer_radius=pcbnew.FromMM(32.)
    )
)

OPT.lines.n_comps = OPT.lines.n_lines * (OPT.lines.n_leds + 1)
OPT.lines.led_ref = lambda line_idx, led_idx: '%s%d' % (OPT.lines.led_pfx, line_idx * OPT.lines.n_leds + led_idx)
OPT.lines.res_ref = lambda line_idx: '%s%d' % (OPT.lines.res_pfx, line_idx)


def get_lines(board, component_only):
    for line_idx in range(OPT.lines.n_lines):
        comp = board.components[OPT.lines.res_ref(line_idx)]
        yield comp if component_only else (comp, False)
        for led_idx in range(OPT.lines.n_leds):
            comp = board.components[OPT.lines.led_ref(line_idx, led_idx)]
            yield comp if component_only else (comp, True)


def place_lines(board):
    angle = OPT.lines.init_angle
    place = Component.place_pads_on_circ if OPT.lines.pad_on_circ else Component.place_radial
    for comp, is_led in get_lines(board, False):
        # Center on the spanned angle (here is where we assume that the two pads are symmetric)
        angle += OPT.lines.spanned_angles[comp.name] / 2.
        place(comp, angle, OPT.lines.radius, orientation=OPT.lines.led_orient if is_led else OPT.lines.res_orient)
        angle += OPT.lines.angle_step + OPT.lines.spanned_angles[comp.name] / 2.


def route_led_lines(board):
    for net in board.netlist.values():
        if len(net.terminals) != 2:
            continue
        if net.terminals[0].component.flag_placed and net.terminals[1].component.flag_placed:
            del net.tracks[:]
            net.route_arc()


def route_rings(board, **kwargs):
    kwargs['skip_start'] = False
    kwargs['include_end'] = True
    for net in board.netlist.values():
        if net.flag_routed or len(net.terminals) != OPT.lines.n_lines + 1:
            continue
        # Check if this has n LED or ring terminals
        cnt_led = len(filter(lambda x: x.component.name.startswith(OPT.lines.led_pfx) and x.component.flag_placed,
                             net.terminals))
        cnt_res = len(filter(lambda x: x.component.name.startswith(OPT.lines.res_pfx) and x.component.flag_placed,
                             net.terminals))
        if cnt_res == 0 and cnt_led == OPT.lines.n_lines:
            radius = OPT.rings.gnd_radius
            overhang = OPT.rings.overhang
        elif cnt_res == OPT.lines.n_lines and cnt_led == 0:
            radius = OPT.rings.pwr_radius
            overhang = -OPT.rings.overhang
        else:
            continue
        # Ok that's one of the two ring nets.
        OPT.ring_nets.append(net.name)
        del net.tracks[:]
        intersection_angles = []
        for t in filter(lambda x: x.component.flag_placed, net.terminals):
            # Get the pad position
            term_pol = t.position.to_polar()
            # Decide the endpoint for the arc
            arc_endpt = Polar(term_pol.a + overhang, term_pol.r)
            # Draw an arc to that point
            net.tracks.append(Track(map(Polar.to_point, apx_arc_through_polars(term_pol, arc_endpt, **kwargs))))
            # Draw a segment down to the given radius
            net.tracks.append(Track([arc_endpt.to_point(), Polar(arc_endpt.a, radius).to_point()]))
            # Angle at which it intersects the ring
            intersection_angles.append(arc_endpt.a)
        # Ok now join all the pieces. Add all pieces at multiples of 15 degrees so that we can attach at several angles
        intersection_angles += list(map(lambda x: float(x) * math.pi / 6., range(24)))
        intersection_angles = list(sorted(map(normalize_angle, intersection_angles)))
        # Ok pairwise arcs
        p1 = Polar(intersection_angles[-1], radius)
        for angle in intersection_angles:
            p2 = Polar(angle, radius)
            net.tracks.append(Track(map(Polar.to_point, apx_arc_through_polars(p1, p2, **kwargs))))
            p1 = p2


def compute_lines_spanned_angles(board):
    # Compute how many radians do the resistor and the LED's pad span
    def get_spanned_angle(comp):
        c = Chord(OPT.lines.radius, 0., 0.).with_length(comp.get_pads_distance())
        # We make the assumption that the center is at the... center
        if abs(comp.pads.values()[0].offset.l2() - comp.pads.values()[1].offset.l2()) > 0.001:
            print(('Component will be misaligned because %s has two pads which are not symmetric.' % comp.name),
                  file=sys.stderr)
        if not OPT.lines.pad_on_circ:
            c = c.with_distance_to_origin(OPT.lines.radius)
        return c.aperture
    return {comp.name: get_spanned_angle(comp) for comp in get_lines(board, True)}


def add_copper_pours(board):
    for net in board.netlist.values():
        if not net.flag_routed or len(net.terminals) != 2:
            continue
        # Add a fill on top of it
        if OPT.pours.parallel_to_comp:
            t1, t2 = net.terminals
            a1 = t1.component.position.to_polar().a
            a2 = t2.component.position.to_polar().a
            shift1 = t1.component.get_pad_tangential_distance(t1.pad)
            shift2 = t2.component.get_pad_tangential_distance(t2.pad)
        else:
            a1 = net.terminals[0].position.to_polar().a
            a2 = net.terminals[1].position.to_polar().a
            shift1 = 0.
            shift2 = 0.
        net.fills.append(Fill(
            list(map(Polar.to_point, apx_crown_sector(a1, a2, OPT.pours.inner_radius, OPT.pours.outer_radius,
                                                      shift1, shift2)))))
    # Add copper pours for the remaining pads
    for net_name in OPT.ring_nets:
        net = board.netlist[net_name]
        for t in filter(lambda x: x.component.flag_placed, net.terminals):
            # Which direction is the overhang?
            if t.component.name.startswith(OPT.lines.res_pfx):
                overhang = -OPT.pours.overhang
            elif t.component.name.startswith(OPT.lines.led_pfx):
                overhang = OPT.pours.overhang
            else:
                continue
            if OPT.pours.parallel_to_comp:
                a1 = t.component.position.to_polar().a
                a2 = t.position.to_polar().a
                a2 += OPT.lines.angle_step * (0.5 if overhang > 0. else -0.5)
                shift1 = t.component.get_pad_tangential_distance(t.pad)
                # Compute how much space is left
                c = Chord(OPT.lines.radius, OPT.lines.angle_step - 2. * OPT.pours.overhang)
                c = c.with_distance_to_origin(OPT.lines.radius)
                shift2 = c.length * (0.5 if overhang > 0. else -0.5)
            else:
                a1 = t.position.to_polar().a
                a2 = a1 + overhang
                shift1 = 0.
                shift2 = 0.
            net.fills.append(Fill(
                list(map(Polar.to_point, apx_crown_sector(a1, a2, OPT.pours.inner_radius, OPT.pours.outer_radius,
                                                          shift1, shift2)))))

def main():
    board = FromPCB.populate()
    # Compute how much angle is reserved for each component
    OPT.lines.spanned_angles = compute_lines_spanned_angles(board)
    # Space between each components's pads
    OPT.lines.angle_step = (2. * math.pi - sum(OPT.lines.spanned_angles.values())) / OPT.lines.n_comps
    # Angular shift to get free space at angle 0
    OPT.lines.init_angle = OPT.lines.angle_step / 2.
    # Extra segment of wiring overhanging from the pwr (gnd) pad of the resistor (led)
    OPT.rings.overhang = OPT.lines.angle_step / 3.
    OPT.pours.overhang = 3. * OPT.lines.angle_step / 7.
    OPT.ring_nets = []
    # Place all leds and resistors in F.Cu
    place_lines(board)
    # Connect adjacent pads on F.Cu
    route_led_lines(board)
    # Bring power to the resistor and ground from the LEDs onto two other concentric rings
    route_rings(board)
    # Add copper pours on the front face
    add_copper_pours(board)
    # Save
    ToPCB.apply(board)


if __name__ == '__main__':
    main()
