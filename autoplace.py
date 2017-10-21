from __future__ import unicode_literals
from radial import RadialPlacer, Place, compute_radial_segment
import math
from collections import namedtuple

import pcbnew as pcb

Terminal = namedtuple('Terminal', ['module', 'pad'])

class Illuminator(object):

    def get_two_terminal_nets_between_placed_modules(self):
        nets = {}
        for mod_name in self.placed_modules:
            mod = self.board.FindModule(mod_name)
            for pad in mod.Pads():
                net = pad.GetNet()
                net_code = pad.GetNetCode()
                if net_code not in nets:
                    nets[net_code] = []
                nets[net_code].append(Terminal(module=mod_name, pad=pad.GetPadName()))
        return {net_code: entries for net_code, entries in nets.items()
            if len(entries) == 2
                and entries[0].module in self.placed_modules
                and entries[1].module in self.placed_modules
        }

    def clear_tracks_in_nets(self, net_codes):
        for track in self.board.GetTracks():
            if track.GetNetCode() in net_codes:
                self.board.Delete(track)

    def place_module(self, name, place):
        mod = self.board.FindModule(name)
        if mod:
            self.placed_modules.add(name)
            mod.SetPosition(pcb.wxPointMM(place.x, place.y))
            mod.SetOrientation(-math.degrees(place.rot) * 10.)

    def place(self, *args, **kwargs):
        placer = RadialPlacer(*args, **kwargs)
        for name, place in placer():
            print('Placing %s at %s.' % (name, str(place)))
            self.place_module(name, place)
        self.center = pcb.wxPoint(pcb.FromMM(placer.center.x), pcb.FromMM(placer.center.y))

    def make_track_segment(self, start, end, net_code):
        t = pcb.TRACK(self.board)
        self.board.Add(t)
        t.SetStart(start)
        t.SetEnd(end)
        t.SetNetCode(net_code)
        t.SetLayer(0)
        return t

    def route(self):
        nets = self.get_two_terminal_nets_between_placed_modules()
        self.clear_tracks_in_nets(nets.keys())
        for net_code, (start, end) in nets.items():
            print('Routing net %s (from %s, pad %s to %s, pad %s) with a radial segment.' %
                (self.board.FindNet(net_code).GetNetname(),
                    start.module, start.pad, end.module, end.pad))
            # Get the offsetted position of the pads
            start_pos = self.board.FindModule(start.module).FindPadByName(start.pad).GetPosition()
            end_pos = self.board.FindModule(end.module).FindPadByName(end.pad).GetPosition()
            last_pos = start_pos
            for x, y in compute_radial_segment(self.center, start_pos, end_pos, 10):
                new_pos = pcb.wxPoint(x, y)
                track_seg = self.make_track_segment(last_pos, new_pos, net_code)
                last_pos = new_pos

    def __init__(self):
        super(Illuminator, self).__init__()
        self.placed_modules = set()
        self.board = pcb.GetBoard()
        self.center = None

if __name__ == '__main__':
    a = Illuminator()
    a.place()
    a.route()
