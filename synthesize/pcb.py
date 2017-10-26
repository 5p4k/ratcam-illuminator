from __future__ import unicode_literals
from collections import namedtuple
from polar import *
import cad
import pcbnew as pcb


NetPlaceholder = namedtuple('NetPlaceholder', ['name', 'code'])


def _conv_point(pt):
    return Point(float(pt.x), float(pt.y))


def _conv_vector(pt):
    return Vector(float(pt.x), float(pt.y))


def _conv_pad(pad):
    name = pad.GetName()
    pos0 = pad.GetPos0()
    size = pad.GetSize()
    net = NetPlaceholder(name=pad.GetNetname(), code=pad.GetNetCode())
    return cad.Pad(name, offset=_conv_vector(pos0), connected_to=net, size=_conv_vector(size))


def _conv_component(modu):
    reference = modu.GetReference()
    pads = map(_conv_pad, modu.Pads())
    return cad.Component(reference, pads)


def populate():
    board = cad.Board()
    for modu in pcb.GetBoard().GetModules():
        comp = _conv_component(modu)
        board.components[comp.name] = comp
    for comp in board.components.values():
        for pad in comp.pads.values():
            net_name, net_code = pad.connected_to
            if net_name is None or net_code is None:
                continue
            terminal = cad.Terminal(comp, pad)
            if net_name in board.netlist:
                board.netlist[net_name].terminals.append(terminal)
            else:
                board.netlist[net_name] = cad.Net(net_name, net_code, [terminal])
    return board
