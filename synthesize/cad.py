from __future__ import unicode_literals
import math
from polar import Polar, Chord, Point, apx_arc_through_polars, normalize_angle
from enum import Enum


class Layer(Enum):
    F_Cu = 0
    B_Cu = 31


class Via(object):
    def __repr__(self):
        return 'Via(%s)' % repr(self.position)

    def __str__(self):
        return repr(self)

    def __init__(self, position):
        self.position = position


class Track(object):
    def __repr__(self):
        return 'Track(%s, %s)' % (repr(self.points), repr(self.layer))

    def __str__(self):
        return 'Track(%s)' % str(self.points)

    def __init__(self, points, layer=Layer.F_Cu):
        self.points = list(points)
        self.layer = layer


class Fill(object):
    def __repr__(self):
        return 'Fill(%s, %s)' % (repr(self.points), repr(self.layer))

    def __str__(self):
        return 'Fill(%s)' % str(self.points)

    def __init__(self, points, layer=Layer.F_Cu):
        self.points = list(points)
        self.thermal = False
        self.layer = layer


class Terminal(object):
    def load_objects(self, board):
        if isinstance(self.component, unicode) or isinstance(self.component, str):
            self.component = board.components.get(self.component, self.component)
        if isinstance(self.component, Component) and (isinstance(self.pad, str) or isinstance(self.pad, unicode)):
            self.pad = self.component.pads.get(self.pad, self.pad)

    @property
    def position(self):
        return self.component.get_pad_position(self.pad)

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

    def route_arc(self, center=Point(0., 0.), **kwargs):
        if len(self.terminals) != 2:
            raise RuntimeError()
        s = (self.terminals[0].position - center).to_polar()
        t = (self.terminals[1].position - center).to_polar()
        kwargs['skip_start'] = False
        kwargs['include_end'] = True
        self.tracks.append(Track(map(lambda pol: center + pol.to_point().to_vector(),
                                     apx_arc_through_polars(s, t, **kwargs))))
        self.flag_routed = True

    def route_straight(self):
        if len(self.terminals) != 2:
            raise RuntimeError()
        self.tracks.append(Track([self.terminals[0].position, self.terminals[1].position]))
        self.flag_routed = True

    def __repr__(self):
        return 'Net(%s, %s, %s)' % (repr(self.name), repr(self.code), repr(self.terminals))

    def __str__(self):
        return str(self.name) + str(list(map(str, self.terminals)))

    def __init__(self, name, code, terminals):
        self.name = name
        self.code = code
        self.terminals = terminals
        self.tracks = []
        self.fills = []
        self.flag_routed = False


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

    def _pad(self, pad):
        if isinstance(pad, str) or isinstance(pad, unicode):
            return self.pads[pad]
        else:
            if pad not in self.pads.values():
                raise ValueError()
            return pad

    def _two_pads(self, pad1, pad2):
        if (pad1 is None) != (pad2 is None):
            raise ValueError()
        if pad1 is None and pad2 is None:
            if len(self.pads) != 2:
                raise RuntimeError()
            else:
                pad1, pad2 = self.pads.values()
        else:
            pad1 = self._pad(pad1)
            pad2 = self._pad(pad2)
        return pad1, pad2

    def get_pad_tangential_distance(self, pad):
        if pad not in self.pads.values():
            raise ValueError()
        # Tangent angle
        tan_angle = self.position.to_polar().a - math.pi / 2.
        # Pad offset wrt tangent
        return pad.offset.rotated(self.orientation - tan_angle).dx

    def get_pad_position(self, pad):
        if pad not in self.pads.values():
            raise ValueError()
        return self.position + pad.offset.rotated(self.orientation)

    def place_radial(self, angle, radius, orientation=0.):
        self.orientation = orientation + angle - math.pi / 2.
        self.position = Polar(angle, radius).to_point()
        self.flag_placed = True

    def place_pads_on_circ(self, angle, radius, pad1=None, pad2=None, orientation=0.):
        pad1, pad2 = self._two_pads(pad1, pad2)
        chord = Chord(radius, 0., angle).with_length(self.get_pads_distance(pad1, pad2))
        self.align_pads_to_chord(chord, orientation=orientation)
        self.flag_placed = True

    def get_pads_distance(self, pad1=None, pad2=None):
        pad1, pad2 = self._two_pads(pad1, pad2)
        return (pad1.offset - pad2.offset).l2()

    def align_pads_to_chord(self, chord, pad1=None, pad2=None, orientation=0.):
        pad1, pad2 = self._two_pads(pad1, pad2)
        assert(abs(chord.length - self.get_pads_distance(pad1, pad2)) < 0.001)
        # Compute the natural pad inclination
        pads_angle = normalize_angle(orientation + (pad2.offset - pad1.offset).to_polar().a)
        # Apply the correct orientation
        self.orientation = (chord.declination - math.pi / 2.) + (pads_angle - math.pi)
        # Now get the correct, transformed offset and move the component in place
        if pads_angle < math.pi / 2. or pads_angle > 3. * math.pi / 2.:
            chord_endpt = chord.endpoints[1]
        else:
            chord_endpt = chord.endpoints[0]
        self.position = chord_endpt.to_point() + (self.get_pad_position(pad1) - self.position)

    def __init__(self, name, pads, position=None, orientation=None, flipped=False):
        self.name = name
        self.position = position
        self.orientation = orientation
        self.flipped = flipped
        self.flag_placed = False
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
