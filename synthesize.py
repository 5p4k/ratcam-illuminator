from __future__ import unicode_literals
from radial import RadialPlacer, Place, compute_radial_segment, shift_along_radius, shift_along_arc
import math
from collections import namedtuple

import pcbnew as pcb

# Leds will be named LED0, LED1...
LED_PREFIX = 'LED'
# Resistor driving LEDS will be named R0, R1, ...
RESISTOR_PREFIX = 'R'
# Coordinated of the center in mm
CENTER_X_MM = 100.
CENTER_Y_MM = 100.
# Radius of the circle where the center of the components
# (leds and resistor) is placed
RADIUS_MM = 30.
# Number of lines of LED (= number of resistors)
N_LINES = 3
# Number of leds per line
N_LEDS_PER_LINE = 3
# Offset angle for the whole design
ROTATION_OFS_RAD = -math.pi / 12.
# Offset angle of the LEDs
LED_ORIENTATION_OFS_RAD = math.pi
# Offset angle of the resistors
RESISTOR_ORIENTATION_OFS_RAD = 0.
# Angular resolution for synthesizing arcs
ANGULAR_RESOLUTION = math.pi / 40
# True for having the power ring on F.Cu (False resp. for B.Cu)
PWR_RING_FCU = True
# True for having the ground ring on F.Cu (False resp. for B.Cu)
GND_RING_FCU = True
# Radial offset in mm for the power ring
PWR_RING_DISP_MM = 4.
# Radial offset in mm for the ground ring
GND_RING_DISP_MM = -4.
# Extra portion of wire to add before connecting to a ring
_ANG_DIST_BTW_MODS = 2. * math.pi / float((1 + N_LEDS_PER_LINE) * N_LINES)
RING_OVERHANG_ANGLE = _ANG_DIST_BTW_MODS / 4.
# If >0, routes the LED strips with a copper fill
LED_FILL_WIDTH_MM = 4.
DEFAULT_TRACK_WIDTH_MM=1.

# _FILL_OVERHANG_ANGLE = math.asin(DEFAULT_TRACK_WIDTH_MM / (4. * RADIUS_MM))
_FILL_OVERHANG_ANGLE = (_ANG_DIST_BTW_MODS - 2. * RING_OVERHANG_ANGLE) / 6.

Terminal = namedtuple('Terminal', ['module', 'pad'])

LayerBCu = 31
LayerFCu = 0
NetTypeLedStrip = 'led strip'
NetTypePower = 'power'
NetTypeGround = 'ground'
NetTypeUnknown = '?'

class Illuminator(object):

    def guess_net_type(self, terminals):
        all_leds = True
        all_resistors = True
        for t in terminals:
            if t.module.startswith(LED_PREFIX):
                all_resistors = False
            elif t.module.startswith(RESISTOR_PREFIX):
                all_leds = False
        if all_leds != all_resistors:
            if all_resistors:
                # 2+ resistors connected: power
                return NetTypePower
            elif len(terminals) != 2:
                # 1 or 3+ led connected: ground
                return NetTypeGround
            else:
                # If it's the same pad, it's ground,
                # otherwise, Strip
                if terminals[0].pad == terminals[1].pad:
                    return NetTypeGround
                else:
                    return NetTypeLedStrip
        elif not all_leds and len(terminals) == 2:
            # Mixed resistor/led 2-terminal net. That's a strip
            return NetTypeLedStrip
        else:
            return NetTypeUnknown


    def get_nets_at_placed_modules(self):
        retval = {}
        for mod_name in self.placed_modules:
            mod = self.board.FindModule(mod_name)
            for pad in mod.Pads():
                net = pad.GetNet()
                net_code = pad.GetNetCode()
                if net_code not in retval:
                    retval[net_code] = []
                retval[net_code].append(Terminal(module=mod_name, pad=pad.GetPadName()))
        return retval

    def clear_tracks_in_nets(self, net_codes):
        for track in self.board.GetTracks():
            if track.GetNetCode() in net_codes:
                self.board.Delete(track)
        for i in range(self.board.GetAreaCount()):
            area = self.board.GetArea(i)
            if area.GetNetCode() in net_codes:
                self.board.Delete(area)

    def place_module(self, name, place):
        mod = self.board.FindModule(name)
        if mod:
            self.placed_modules.add(name)
            mod.SetPosition(pcb.wxPoint(place.x, place.y))
            mod.SetOrientation(-math.degrees(place.rot) * 10.)

    def get_terminal_position(self, terminal):
        return self.board.FindModule(terminal.module).FindPadByName(terminal.pad).GetPosition()

    def get_module_position(self, module):
        return self.board.FindModule(module).GetPosition()

    def get_net_name(self, net_code):
        return self.board.FindNet(net_code).GetNetname()

    def place(self):
        placer = RadialPlacer(
            n_lines=N_LINES,
            n_leds_per_line=N_LEDS_PER_LINE,
            radius=pcb.FromMM(RADIUS_MM),
            center=Place(
                x=pcb.FromMM(CENTER_X_MM),
                y=pcb.FromMM(CENTER_Y_MM),
                rot=ROTATION_OFS_RAD),
            led_orientation=LED_ORIENTATION_OFS_RAD,
            resistor_orientation=RESISTOR_ORIENTATION_OFS_RAD,
            led_prefix=LED_PREFIX,
            resistor_prefix=RESISTOR_PREFIX
        )
        placer.print_settings()
        for name, place in placer():
            print('Placing %s at %s.' % (name, str(place)))
            self.place_module(name, place)
        self.center = pcb.wxPoint(placer.center.x, placer.center.y)

    def make_track_segment(self, start, end, net_code, layer):
        t = pcb.TRACK(self.board)
        self.board.Add(t)
        t.SetStart(start)
        t.SetEnd(end)
        t.SetNetCode(net_code)
        t.SetLayer(layer)
        t.SetWidth(pcb.FromMM(DEFAULT_TRACK_WIDTH_MM))
        return end

    def _make_track_arc_internal(self, start, net_code, layer, *args, **kwargs):
        last = start
        for pt in compute_radial_segment(self.center, start, *args, **kwargs):
            self.make_track_segment(last, pt, net_code, layer)
            last = pt
        return last

    def make_track_arc_from_endpts(self, start, end, net_code, layer):
        return self._make_track_arc_internal(
            start, net_code, layer,
            end=end, angular_resolution=ANGULAR_RESOLUTION)

    def make_track_arc_from_angle(self, start, angle, net_code, layer):
        return self._make_track_arc_internal(
            start, net_code, layer,
            angle=angle, angular_resolution=ANGULAR_RESOLUTION)

    def make_track_radial_segment(self, pos, displacement, net_code, layer):
        end_pos = shift_along_radius(self.center, pos, displacement)
        return self.make_track_segment(pos, end_pos, net_code, layer)

    def make_fill_area(self, vertices, is_thermal, net_code, layer):
        area = self.board.InsertArea(net_code, self.board.GetAreaCount(), layer,
            vertices[0].x, vertices[0].y, pcbnew.CPolyLine.DIAGONAL_EDGE)
        if is_thermal:
            area.SetPadConnection(pcb.PAD_ZONE_CONN_THERMAL)
        else:
            area.SetPadConnection(pcb.PAD_ZONE_CONN_FULL)
        # area.SetIsFilled(True)
        outline = area.Outline()
        for vertex in vertices[1:]:
            outline.AppendCorner(vertex.x, vertex.y)
        outline.CloseLastContour()
        area.BuildFilledSolidAreasPolygons(self.board)
        return area

    def make_fill_arc(self, start, end, width, is_thermal, net_code, layer):
        # Compute the vertices
        lower_arc_start = shift_along_radius(self.center, start, -width / 2.)
        upper_arc_start = shift_along_radius(self.center, end, width / 2.)
        vertices = list(compute_radial_segment(self.center,
                lower_arc_start,
                shift_along_radius(self.center, end, -width / 2.),
                angular_resolution=ANGULAR_RESOLUTION,
                excess_angle=0.00001,
                skip_start=False)) + \
            list(compute_radial_segment(self.center,
                upper_arc_start,
                shift_along_radius(self.center, start, width / 2.),
                angular_resolution=ANGULAR_RESOLUTION,
                excess_angle=0.00001,
                skip_start=False))
        return self.make_fill_area(vertices, is_thermal, net_code, layer)

    def make_via(self, position, net_code):
        v = pcb.VIA(self.board)
        self.board.Add(v)
        v.SetPosition(position)
        v.SetViaType(pcb.VIA_THROUGH)
        v.SetLayerPair(LayerFCu, LayerBCu)
        v.SetNetCode(net_code)
        return position

    def _route_arc(self, net_code, start_terminal, end_terminal):
        print('Routing %s between %s and %s with a single arc.' % (
            self.get_net_name(net_code), start_terminal.module, end_terminal.module
        ))
        # Get the offsetted position of the pads
        self.make_track_arc_from_endpts(
            self.get_terminal_position(start_terminal),
            self.get_terminal_position(end_terminal),
            net_code,
            LayerFCu
        )

    def _route_fill_arc(self, net_code, start_terminal, end_terminal):
        print('Routing %s between %s and %s with filled arc region.' % (
            self.get_net_name(net_code), start_terminal.module, end_terminal.module
        ))
        start_pos = self.get_terminal_position(start_terminal)
        end_pos = self.get_terminal_position(end_terminal)
        self.make_track_arc_from_endpts(
            start_pos,
            end_pos,
            net_code,
            LayerFCu
        )
        # Get the offsetted position of the pads
        self.make_fill_arc(
            start_pos,
            end_pos,
            pcb.FromMM(LED_FILL_WIDTH_MM),
            False,
            net_code,
            LayerFCu
        )

    def _route_ring(self, net_code, terminals, displacement, ring_overhang, layer):
        log_msg = 'Routing %s between %s with' % (
            self.get_net_name(net_code), ', '.join([t.module for t in terminals])
        )
        if layer != LayerFCu:
            log_msg += ' a via and'
        if displacement == 0.:
            log_msg += ' a full circular track.'
        else:
            log_msg += ' a circular track offsetted by %f.' % displacement
        terminal_pos = []
        for terminal in terminals:
            term_ring_pt = self.get_terminal_position(terminal)
            if displacement != 0.:
                if ring_overhang != 0.:
                    new_end_pt = shift_along_arc(self.center, term_ring_pt, ring_overhang)
                    self.make_track_arc_from_endpts(term_ring_pt, new_end_pt, net_code, LayerFCu)
                    if LED_FILL_WIDTH_MM != 0.:
                        # Some extra fill:
                        overhand_angle = _FILL_OVERHANG_ANGLE * (1. if ring_overhang > 0. else -1.)
                        fill_end_pt  = shift_along_arc(self.center,
                            new_end_pt, overhand_angle)
                        self.make_fill_arc(term_ring_pt, fill_end_pt,
                            pcb.FromMM(LED_FILL_WIDTH_MM),
                            False, net_code, LayerFCu)
                    term_ring_pt = new_end_pt
                term_ring_pt = self.make_track_radial_segment(
                    term_ring_pt, displacement, net_code, LayerFCu)
            # Now add the via and store the position
            if layer != LayerFCu:
                self.make_via(term_ring_pt, net_code)
            terminal_pos.append(term_ring_pt)
        # Connect the terminals with an arc
        last_pos = terminal_pos[-1]
        for pos in terminal_pos:
            self.make_track_arc_from_endpts(last_pos, pos, net_code, layer)
            last_pos = pos

    def route(self):
        got_power = False
        got_ground = False
        for net_code, terminals in self.get_nets_at_placed_modules().items():
            # Try to guess net type
            net_type = self.guess_net_type(terminals)
            print('Net %s guessed type: %s' % (self.get_net_name(net_code), net_type))
            if net_type == NetTypeUnknown:
                print('I do not know what to to with net %s between %s...' % (
                    self.get_net_name(net_code),
                    str(terminals)
                ))
                continue
            # Clear this net
            self.clear_tracks_in_nets([net_code])
            if net_type == NetTypeLedStrip:
                assert(len(terminals) == 2)
                if LED_FILL_WIDTH_MM > 0.:
                    self._route_fill_arc(net_code, terminals[0], terminals[1])
                else:
                    self._route_arc(net_code, terminals[0], terminals[1])
            elif net_type == NetTypePower:
                assert(not got_power)
                got_power = True
                self._route_ring(net_code, terminals,
                    pcb.FromMM(PWR_RING_DISP_MM),
                    RING_OVERHANG_ANGLE,
                    LayerFCu if PWR_RING_FCU else LayerBCu
                )
            elif net_type == NetTypeGround:
                assert(not got_ground)
                got_ground = True
                self._route_ring(net_code, terminals,
                    pcb.FromMM(GND_RING_DISP_MM),
                    -RING_OVERHANG_ANGLE,
                    LayerFCu if GND_RING_FCU else LayerBCu
                )


    def __init__(self):
        super(Illuminator, self).__init__()
        self.placed_modules = set()
        self.board = pcb.GetBoard()
        self.center = None

if __name__ == '__main__':
    a = Illuminator()
    a.place()
    a.route()
