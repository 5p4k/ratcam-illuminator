from __future__ import unicode_literals
import math


class Terminal(object):
    def load_objects(self, board):
        if isinstance(self.component, unicode) or isinstance(self.component, str):
            self.component = board.components.get(self.component, self.component)
        if isinstance(self.component, Component) and (isinstance(self.pad, str) or isinstance(self.pad, unicode)):
            self.pad = self.component.pads.get(self.pad, self.pad)

    def __repr__(self):
        return 'Terminal(%s, %s)' % (repr(self.component), repr(self.pad))

    def __str__(self):
        if isinstance(self.component, Component):
            comp_name = str(self.component.name)
        else:
            comp_name = str(self.component)
        if isinstance(self.pad, Pad):
            pad_name = str(self.pad.name)
        else:
            pad_name = str(self.pad)
        return '%s.%s' % (comp_name, pad_name)

    def __init__(self, component, pad):
        self.component = component
        self.pad = pad


class Net(object):
    def assign_connections(self, board):
        for t in self.terminals:
            t.load_objects(board)
            if isinstance(t.pad, Pad):
                t.pad.connected_to = self

    def other_terminals(self, pad):
        return [t for t in self.terminals if t.pad is not pad]

    def __repr__(self):
        return 'Net(%s, %s, %s)' % (repr(self.name), repr(self.code), repr(self.terminals))

    def __str__(self):
        return str(self.name) + str(list(map(str, self.terminals)))

    def __init__(self, name, code, terminals):
        self.name = name
        self.code = code
        self.terminals = terminals


class Pad(object):
    def __repr__(self):
        return 'Pad(%s)' % repr(self.name)

    def __str__(self):
        return str(self.name)

    def __init__(self, name, offset=None, connected_to=None, size=None):
        self.name = name
        self.offset = offset
        self.connected_to = connected_to
        self.size = size


class Component(object):
    def __repr__(self):
        return 'Component(%s, %s)' % (repr(self.name), repr(self.pads))

    def __str__(self):
        return str(self.name)

    def get_pad_position(self, pad):
        if isinstance(pad, unicode) or isinstance(pad, str):
            pad = self.pads[pad]
        pad_pol = pad.offset.to_polar()
        pad_pol.a += self.orientation
        return self.position + pad_pol.to_point().to_vector()

    def get_two_pads_distance(self):
        if len(self.pads) != 2:
            return None
        pad_a, pad_b = self.pads.values()
        return (pad_a.offset - pad_b.offset).l2()

    def align_pads_to_chord(self, chord, pads=None):
        assert(abs(chord.length - self.get_two_pads_distance()) < 0.001)
        if pads is None:
            pads = self.pads.values()
            pads.sort(key=lambda p: -p.offset.dx)
        if len(pads) != 2:
            raise ValueError()
        rpad, lpad = pads
        if isinstance(rpad, str) or isinstance(rpad, str):
            rpad = self.pads.get(rpad, None)
        if isinstance(lpad, str) or isinstance(lpad, str):
            lpad = self.pads.get(lpad, None)
        if lpad is None or rpad is None:
            raise ValueError()
        # Ok now let's get serious
        lpad_angle = (lpad.offset - rpad.offset).to_polar().a
        self.orientation = chord.declination + lpad_angle - 3. * math.pi / 2.
        self.position = chord.endpoints[0].to_point() - rpad.offset

    def __init__(self, name, pads, position=None, orientation=None):
        self.name = name
        self.position = position
        self.orientation = orientation
        if isinstance(pads, dict):
            self.pads = pads
        else:
            self.pads = {pad.name: pad for pad in pads}


class Board(object):
    def assign_connections(self):
        for n in self.netlist.values():
            n.assign_connections(self)

    def __repr__(self):
        return 'Board(%s, %s)' % (repr(self.components), repr(self.netlist))

    def __init__(self):
        self.components = {}
        self.netlist = {}
