from __future__ import unicode_literals


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

    def __init__(self, name, pads):
        self.name = name
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
