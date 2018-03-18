from __future__ import unicode_literals, print_function
from pcb import ToPCB, FromPCB
from cad import Component, Track, Fill, Via, Layer, Terminal
from polar import Polar, apx_arc_through_polars, normalize_angle, Chord, apx_crown_sector, Point
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
        n_lines=6,
        n_leds=2,
        led_orient=math.pi,
        res_orient=0.,
        radius=pcbnew.FromMM(25.),
        pad_on_circ=True,
        led_pfx='LED',
        res_pfx='R',
        separator=True
    ),
    rings=dotdict(
        pwr_radius=pcbnew.FromMM(28.),
        gnd_radius=pcbnew.FromMM(22.)
    ),
    pours=dotdict(
        parallel_to_comp=False,
        inner_radius=pcbnew.FromMM(23.5),
        outer_radius=pcbnew.FromMM(26.5)
    ),
    track_width=pcbnew.FromMM(1.),
    via_diam=pcbnew.FromMM(1.),
    via_drill_diam=pcbnew.FromMM(0.4),
    connector='J0',
    mosfet='Q0'
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
        if not is_led and OPT.lines.separator:
            angle += OPT.lines.separator_spanned_angle + OPT.lines.angle_step
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
            # Ok that's one of the two ring nets.
            OPT.rings.gnd_net = net.name
            radius = OPT.rings.gnd_radius
            overhang = OPT.rings.overhang
        elif cnt_res == OPT.lines.n_lines and cnt_led == 0:
            # Ok that's one of the two ring nets.
            OPT.rings.pwr_net = net.name
            radius = OPT.rings.pwr_radius
            overhang = -OPT.rings.overhang
        else:
            continue
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
    for net_name in [OPT.rings.pwr_net, OPT.rings.gnd_net]:
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


class ConnMosfRadiusTranslator(object):
    @classmethod
    def _translate(cls, r, direct, x1, y1, x2, y2):
        if direct:
            return -(math.sqrt((r + x1) * (r + x1) + y1 * y1 - y2 * y2) + x2)
        else:
            return math.sqrt((r + x1) * (r + x1) + y1 * y1 - y2 * y2) - x2

    def _translate_conn_to_mosf(self, r, i):
        return self.__class__._translate(r, True,
                                         self._conn_pad_ofs[i].dx, self._conn_pad_ofs[i].dy,
                                         self._mosf_pad_ofs[i].dx, self._mosf_pad_ofs[i].dy,)

    def _translate_mosf_to_conn(self, r, i):
        return self.__class__._translate(r, False,
                                         self._mosf_pad_ofs[i].dx, self._mosf_pad_ofs[i].dy,
                                         self._conn_pad_ofs[i].dx, self._conn_pad_ofs[i].dy)

    def conn_to_mosf(self, r):
        radii = map(lambda i: self._translate_conn_to_mosf(r, i), range(0, len(self._conn_pad_ofs)))
        return max(radii) if self._conn_pad_ofs[0].dx >= 0. else min(radii)

    def mosf_to_conn(self, r):
        radii = map(lambda i: self._translate_mosf_to_conn(r, i), range(0, len(self._conn_pad_ofs)))
        return min(radii) if self._conn_pad_ofs[0].dx >= 0. else max(radii)

    def __init__(self, conn_pad_ofs, mosf_pad_ofs):
        self._conn_pad_ofs = list(conn_pad_ofs)
        self._mosf_pad_ofs = list(mosf_pad_ofs)
        assert (len(self._conn_pad_ofs) == len(self._mosf_pad_ofs))


def orient_connector_and_mosfet_relative(conn, mosf):
    nets = set([pad.connected_to for pad in conn.pads.values()])
    nets.intersection_update(set([pad.connected_to for pad in mosf.pads.values()]))
    # Make sure the two involved pads both face north or south
    for net in nets:
        t1_pos, t2_pos = map(lambda t: t.position, filter(lambda t: t.component in [conn, mosf], net.terminals))
        if (t1_pos.y >= 0) != (t2_pos.y >= 0):
            # Rotate one
            mosf.orientation += math.pi


def orient_connector_and_mosfet(conn, mosf):
    # Two pads are interconnected, but one for each is connected either to pwr or to gnd
    conn_pwr_pad = next(pad for pad in conn.pads.values() if pad.connected_to.name == OPT.rings.pwr_net)
    # Check which one is on the right
    conn_pwr_pad_east = (conn.get_pad_offset(conn_pwr_pad).dx > 0)
    conn_oriented_correctly = (conn_pwr_pad_east == (OPT.rings.pwr_radius > OPT.lines.radius))
    # Fix the orientation
    if not conn_oriented_correctly:
        mosf.orientation += math.pi
        conn.orientation += math.pi
    # We only care about the connector. After all, if they're both oriented in the wrong direction, this will fix
    # the issue. If only one is oriented in the wrong direction, that's better if it's the mosfet
    conn_to_mosf_pads = [pad for pad in conn.pads.values() if pad.connected_to.name != OPT.rings.pwr_net]
    OPT.rings.mosf_conn_nets = [pad.connected_to.name for pad in conn_to_mosf_pads]
    mosf_to_conn_pads = map(lambda pad: pad.connected_to.other_terminals(pad)[0].pad, conn_to_mosf_pads)
    OPT.radius_translator = ConnMosfRadiusTranslator(
        [conn.get_pad_offset(pad) for pad in conn_to_mosf_pads],
        [mosf.get_pad_offset(pad) for pad in mosf_to_conn_pads]
    )


def negotiate_connector_and_mosfet_position(conn, mosf):
    # The variable is the connector center's radius. Constraints are expressed as a pair (min, max) of values for x
    r_min = min(OPT.rings.gnd_radius, OPT.rings.pwr_radius) - OPT.track_width / 2.
    r_max = max(OPT.rings.gnd_radius, OPT.rings.pwr_radius) + OPT.track_width / 2.
    constraints = []
    for pad in conn.pads.values():
        # Each pad should not exceed the min-max radius
        ofs = conn.get_pad_offset(pad)
        sz = pad.size
        # x + ofs.dx + sz.dx / 2 < r_max
        constraints.append((-float('inf'), r_max - ofs.dx - sz.dx / 2.))
        # r_min < x + ofs.dx - sz.dx / 2
        constraints.append((r_min - ofs.dx + sz.dx / 2., float('inf')))
        # Extra constraint for pwr/gnd pad
        if pad.connected_to.name == OPT.rings.pwr_net:
            if ofs.dx >= 0.:
                # The pwr/gnd pad west end cannot exceed the track
                # x + ofs.dx - sz.dx / 2 <= pwr/gnd_net_radius
                constraints.append((-float('inf'), OPT.rings.pwr_radius - ofs.dx + sz.dx / 2.))
            else:
                # Vice versa
                # pwr/gnd_net_radius <= x + ofs.dx + sz.dx / 2
                constraints.append((OPT.rings.pwr_radius - ofs.dx - sz.dx / 2., float('inf')))
    # Convert the mosfet constraints into connector constraints
    for pad in mosf.pads.values():
        # Each pad should not exceed the min-max radius
        ofs = mosf.get_pad_offset(pad)
        sz = pad.size
        # x + ofs.dx + sz.dx / 2 < -r_min
        constraints.append((OPT.radius_translator.mosf_to_conn(-r_min - ofs.dx - sz.dx / 2.), float('inf')))
        # -r_max < x + ofs.dx - sz.dx / 2
        constraints.append((-float('inf'), OPT.radius_translator.mosf_to_conn(-r_max - ofs.dx + sz.dx / 2.)))
        # Extra constraint for pwr/gnd pad
        if pad.connected_to.name == OPT.rings.gnd_net:
            if ofs.dx >= 0.:
                # The pwr/gnd pad west end cannot exceed the track
                # x + ofs.dx - sz.dx / 2 <= -pwr/gnd_net_radius
                constraints.append((OPT.radius_translator.mosf_to_conn(-OPT.rings.gnd_radius - ofs.dx + sz.dx / 2.),
                                    float('inf')))
            else:
                # Vice versa
                # -pwr/gnd_net_radius <= x + ofs.dx + sz.dx / 2
                constraints.append((-float('inf'),
                                    OPT.radius_translator.mosf_to_conn(-OPT.rings.gnd_radius - ofs.dx - sz.dx / 2.)))
    for lb, ub in constraints:
        r_min = max(r_min, lb)
        r_max = min(r_max, ub)
    r = (r_min + r_max) / 2.
    conn.position.x = r
    mosf.position.x = OPT.radius_translator.conn_to_mosf(r)
    # Get the routing radius now
    rs = [conn.get_pad_position(pad).to_polar().r for pad in conn.pads.values()
          if pad.connected_to.name != OPT.rings.pwr_net]
    # Min or max?
    pwr_pad = next(pad for pad in conn.pads.values() if pad.connected_to.name == OPT.rings.pwr_net)
    if conn.get_pad_offset(pwr_pad).dx >= 0.:
        # Min
        OPT.rings.mosf_conn_radius = min(rs)
    else:
        # Max
        OPT.rings.mosf_conn_radius = max(rs)


def place_connector_and_mosfet(board):
    conn = board.components[OPT.connector]
    mosf = board.components[OPT.mosfet]
    # Place them at 0, 0 and flip
    conn.position = Point(0., 0.)
    mosf.position = Point(0., 0.)
    conn.orientation = 0.
    mosf.orientation = 0.
    conn.flipped = True
    mosf.flipped = True
    orient_connector_and_mosfet_relative(conn, mosf)
    orient_connector_and_mosfet(conn, mosf)
    negotiate_connector_and_mosfet_position(conn, mosf)


def project_on_ring(pt, radius):
    a = math.asin(pt.y / radius)
    return Polar(a if pt.x >= 0. else math.pi - a, radius).to_point()


def route_connector_and_mosfet(board, **kwargs):
    kwargs['skip_start'] = False
    kwargs['include_end'] = True
    for net_name in OPT.rings.mosf_conn_nets:
        net = board.netlist[net_name]
        t1, t2 = net.terminals
        t1_pos, t2_pos = t1.position, t2.position
        t1_attach_pos = project_on_ring(t1_pos, OPT.rings.mosf_conn_radius)
        t2_attach_pos = project_on_ring(t2_pos, OPT.rings.mosf_conn_radius)
        # Draw segment if needed
        if t1_attach_pos != t1_pos:
            net.tracks.append(Track([t1_pos, t1_attach_pos], Layer.B_Cu))
        if t2_attach_pos != t2_pos:
            net.tracks.append(Track([t2_pos, t2_attach_pos], Layer.B_Cu))
        # Draw a connecting arc
        net.tracks.append(Track(
            map(Polar.to_point, apx_arc_through_polars(t1_attach_pos.to_polar(), t2_attach_pos.to_polar(), **kwargs)),
            Layer.B_Cu
        ))
        net.flag_routed = True
    # And now add a straight segment and a via for the pwr and gnd stuff
    gnd_net = board.netlist[OPT.rings.gnd_net]
    pwr_net = board.netlist[OPT.rings.pwr_net]
    # Find the terminal belonging to the conn/mosfet
    gnd_t = next(t for t in gnd_net.terminals if t.component.name == OPT.mosfet)
    pwr_t = next(t for t in pwr_net.terminals if t.component.name == OPT.connector)
    # Find the correct position and the correct radius
    gnd_pad_pos = gnd_t.position
    gnd_pad_attach_pos = project_on_ring(gnd_pad_pos, OPT.rings.gnd_radius)
    pwr_pad_pos = pwr_t.position
    pwr_pad_attach_pos = project_on_ring(pwr_pad_pos, OPT.rings.pwr_radius)
    # Add a segment if needed
    if gnd_pad_attach_pos != gnd_pad_pos:
        gnd_net.tracks.append(Track([gnd_pad_pos, gnd_pad_attach_pos], Layer.B_Cu))
    if pwr_pad_attach_pos != pwr_pad_pos:
        pwr_net.tracks.append(Track([pwr_pad_pos, pwr_pad_attach_pos], Layer.B_Cu))
    # And the via
    gnd_net.tracks.append(Via(gnd_pad_attach_pos))
    pwr_net.tracks.append(Via(pwr_pad_attach_pos))
    gnd_net.flag_routed = True
    pwr_net.flag_routed = True


def setup_geometry(board):
    # Setup default vias and tracks
    Track.DEFAULT_WIDTH = OPT.track_width
    Via.DEFAULT_DIAMETER = OPT.via_diam
    Via.DEFAULT_DRILL_DIAMETER = OPT.via_drill_diam
    Fill.DEFAULT_FILLET_RADIUS = OPT.track_width / 2.
    # Compute how much angle is reserved for each component
    OPT.lines.spanned_angles = compute_lines_spanned_angles(board)
    # Space to leave between pours:
    OPT.lines.separator_spanned_angle = Chord(OPT.lines.radius, 0., 0.).with_length(OPT.track_width).aperture
    # Space between each components's pads
    if OPT.lines.separator:
        # One extra component: the separator
        consumed_angle = sum(OPT.lines.spanned_angles.values()) + OPT.lines.n_lines * OPT.lines.separator_spanned_angle
        OPT.lines.angle_step = (2. * math.pi - consumed_angle) / (OPT.lines.n_comps + OPT.lines.n_lines)
    else:
        OPT.lines.angle_step = (2. * math.pi - sum(OPT.lines.spanned_angles.values())) / OPT.lines.n_comps
    # Angular shift to get free space at angle 0
    if OPT.lines.separator:
        # We begin with separators so we need to add negative space
        OPT.lines.init_angle = -OPT.lines.separator_spanned_angle / 2.
    else:
        OPT.lines.init_angle = OPT.lines.angle_step / 2.
    # Extra segment of wiring overhanging from the pwr (gnd) pad of the resistor (led)
    if OPT.lines.separator:
        # Overhang track rings until 1 track distance from the end of the copper pour
        OPT.rings.overhang = OPT.lines.angle_step - 1.5 * OPT.lines.separator_spanned_angle
        # Fill until you leave just the separator gap
        OPT.pours.overhang = OPT.lines.angle_step
    else:
        # Overhang track rings by 1/3 of the available space
        OPT.rings.overhang = OPT.lines.angle_step / 3.
        # Fill in until leaving 1 track distance @ OPT.lines.radius
        OPT.pours.overhang = (OPT.lines.angle_step - OPT.lines.separator_spanned_angle) / 2.


def add_mosfet_copper_pours(board):
    mosf = board.components[OPT.mosfet]
    inner_radius = OPT.rings.mosf_conn_radius + (OPT.pours.inner_radius - OPT.lines.radius)
    outer_radius = OPT.rings.mosf_conn_radius + (OPT.pours.outer_radius - OPT.lines.radius)
    for pad in mosf.pads.values():
        if pad.connected_to.name == OPT.rings.gnd_net:
            continue
        # Add a fill on top of it
        if OPT.pours.parallel_to_comp:
            a1 = mosf.position.to_polar().a
            shift = mosf.get_pad_tangential_distance(pad)
        else:
            a1 = mosf.get_pad_position(pad).to_polar().a
            shift = 0.
        if a1 <= math.pi:
            a2 = a1 - OPT.lines.angle_step
        else:
            a2 = a1 + OPT.lines.angle_step
        pad.connected_to.fills.append(Fill(
            list(map(Polar.to_point, apx_crown_sector(a1, a2, inner_radius, outer_radius, shift, 0.))),
            layer=Layer.B_Cu))


def main():
    board = FromPCB.populate()
    # Compute all the angular values according to the selected geometry
    setup_geometry(board)
    # Place all leds and resistors in F.Cu
    place_lines(board)
    # Connect adjacent pads on F.Cu
    route_led_lines(board)
    # Bring power to the resistor and ground from the LEDs onto two other concentric rings
    route_rings(board)
    # Add copper pours on the front face
    add_copper_pours(board)
    # Place smartly J0 and Q0
    # place_connector_and_mosfet(board)
    # Add the metal on B.Cu
    # route_connector_and_mosfet(board)
    # add_mosfet_copper_pours(board)
    # Save
    ToPCB.apply(board)


if __name__ == '__main__':
    main()
