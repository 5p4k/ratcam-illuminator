from __future__ import unicode_literals
from radial import RadialPlacer, Place, compute_radial_segment
import math
from collections import namedtuple

import pcbnew as pcb

LED_PREFIX = 'LED'
RESISTOR_PREFIX = 'R'
RING_DIST_MM = -10.
CENTER_X_MM = 100.
CENTER_Y_MM = 100.
RADIUS_MM = 30.
N_LINES = 3
N_LEDS_PER_LINE = 3
ROTATION_OFS_RAD = 0.
LED_ORIENTATION_OFS_RAD = math.pi
ANGULAR_RESOLUTION = math.pi / 40
PWR_RING_FCU = True
GND_RING_FCU = True
PWR_RING_DISP_MM = 5.
GND_RING_DISP_MM = -5.

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
        return t

    def make_track_arc(self, start, end, net_code, layer):
        last = start
        vertices = compute_radial_segment(
            self.center, start, end,
            angular_resolution=ANGULAR_RESOLUTION)
        retval = []
        for x, y in vertices:
            pt = pcb.wxPoint(x, y)
            retval.append(self.make_track_segment(last, pt, net_code, layer))
            last = pt
        return retval

    def make_track_radial_segment(self, pos, displacement, net_code, layer):
        delta = pos - self.center
        radius = math.sqrt(delta.x * delta.x + delta.y * delta.y)
        scale_factor = float(displacement) / radius
        end_pos = pos + pcb.wxPoint(delta.x * scale_factor, delta.y * scale_factor)
        return self.make_track_segment(pos, end_pos, net_code, layer)


    def make_via(self, position, net_code):
        v = pcb.VIA(self.board)
        self.board.Add(v)
        v.SetPosition(position)
        v.SetViaType(pcb.VIA_THROUGH)
        v.SetLayerPair(LayerFCu, LayerBCu)
        v.SetNetCode(net_code)
        return v

    def _route_arc(self, net_code, start_terminal, end_terminal):
        print('Routing %s between %s and %s with a single arc.' % (
            self.get_net_name(net_code), start_terminal.module, end_terminal.module
        ))
        # Get the offsetted position of the pads
        self.make_track_arc(
            self.get_terminal_position(start_terminal),
            self.get_terminal_position(end_terminal),
            net_code,
            LayerFCu
        )

    def _route_ring(self, net_code, terminals, displacement, layer):
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
                # The radial segment should be orthogonal to the module.
                # Compute it at the center of the module and then move it
                mod_pos = self.get_module_position(terminal.module)
                track_seg = self.make_track_radial_segment(mod_pos,
                    displacement, net_code, LayerFCu)
                track_seg.Move(term_ring_pt - mod_pos)
                # Get the position
                term_ring_pt = track_seg.GetEnd()
            # Now add the via and store the position
            if layer != LayerFCu:
                self.make_via(term_ring_pt, net_code)
            terminal_pos.append(term_ring_pt)
        # Connect the terminals with an arc
        last_pos = terminal_pos[-1]
        for pos in terminal_pos:
            self.make_track_arc(last_pos, pos, net_code, layer)
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
                self._route_arc(net_code, terminals[0], terminals[1])
            elif net_type == NetTypePower:
                assert(not got_power)
                got_power = True
                self._route_ring(net_code, terminals,
                    pcb.FromMM(PWR_RING_DISP_MM),
                    LayerFCu if PWR_RING_FCU else LayerBCu
                )
            elif net_type == NetTypeGround:
                assert(not got_ground)
                got_ground = True
                self._route_ring(net_code, terminals,
                    pcb.FromMM(GND_RING_DISP_MM),
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
