from __future__ import unicode_literals
from collections import namedtuple
from polar import *
import cad
import pcbnew as pcb
import math


NetPlaceholder = namedtuple('NetPlaceholder', ['name', 'code'])


ORIGIN = Point(pcb.FromMM(100.), pcb.FromMM(100.))


class FromPCB(object):
    @staticmethod
    def _conv_angle(angle):
        return -math.radians(float(angle) / 10.)

    @staticmethod
    def _conv_orientation(angle):
        return FromPCB._conv_angle(angle) + math.pi / 2.

    @staticmethod
    def _conv_point(pt):
        return Point(float(pt.x) - ORIGIN.x, ORIGIN.y - float(pt.y))

    @staticmethod
    def _conv_vector(pt):
        return Vector(float(pt.x), -float(pt.y))

    @staticmethod
    def _conv_pad(pad):
        name = pad.GetName()
        pos0 = pad.GetPos0()
        size = pad.GetSize()
        net = NetPlaceholder(name=pad.GetNetname(), code=pad.GetNetCode())
        return cad.Pad(name, offset=FromPCB._conv_vector(pos0), connected_to=net, size=FromPCB._conv_vector(size))

    @staticmethod
    def _conv_component(modu):
        reference = modu.GetReference()
        position = modu.GetPosition()
        orientation = modu.GetOrientation()
        pads = map(FromPCB._conv_pad, modu.Pads())
        return cad.Component(reference, pads, position=FromPCB._conv_point(position),
                             orientation=FromPCB._conv_orientation(orientation))

    @staticmethod
    def populate():
        board = cad.Board()
        for modu in pcb.GetBoard().GetModules():
            comp = FromPCB._conv_component(modu)
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


class ToPCB(object):
    @staticmethod
    def _conv_angle(angle):
        return -math.degrees(float(angle)) * 10.

    @staticmethod
    def _conv_orientation(angle):
        return ToPCB._conv_angle(angle - math.pi / 2.)

    @staticmethod
    def _conv_point(pt):
        return pcb.wxPoint(float(pt.x) + ORIGIN.x, ORIGIN.y - float(pt.y))

    @staticmethod
    def _conv_vector(pt):
        return pcb.wxPoint(float(pt.x), -float(pt.y))

    @staticmethod
    def place_component(comp):
        modu = pcb.GetBoard().FindModule(comp.name)
        modu.SetPosition(ToPCB._conv_point(comp.position))
        modu.SetOrientation(ToPCB._conv_orientation(comp.orientation))

    @staticmethod
    def apply(board):
        for comp in board.components.values():
            ToPCB.place_component(comp)

