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
        return math.radians(float(angle) / 10.)

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
        flipped = modu.IsFlipped()
        pads = map(FromPCB._conv_pad, modu.Pads())
        return cad.Component(reference, pads, position=FromPCB._conv_point(position),
                             orientation=FromPCB._conv_angle(orientation), flipped=flipped)

    @staticmethod
    def _conv_track(trk):
        start = trk.GetStart()
        end = trk.GetEnd()
        layer = trk.GetLayer()
        return cad.Track([start, end], cad.Layer(layer))

    @staticmethod
    def _conv_via(via):
        # Just assume goes from F to B
        return cad.Via(via.GetPosition())

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
        for trk in pcb.GetBoard().GetTracks():
            net_name = trk.GetNetname()
            if net_name in board.netlist:
                if isinstance(trk, pcb.TRACK):
                    board.netlist[net_name].tracks.append(FromPCB._conv_track(trk))
                elif isinstance(trk, pcb.VIA):
                    board.netlist[net_name].tracks.append(FromPCB._conv_via(trk))
        # for area_idx in range(pcb.GetBoard().GetAreaCount()):
        #     area = pcb.GetBoard().GetArea(area_idx)
        #     net_name = area.GetNetname()
        #     if net_name in board.netlist:
        #         board.netlist[net_name].fills.append(FromPCB._conv_fill(area))
        return board


class ToPCB(object):
    @staticmethod
    def _conv_angle(angle):
        return math.degrees(float(angle)) * 10.

    @staticmethod
    def _conv_point(pt):
        return pcb.wxPoint(float(pt.x) + ORIGIN.x, ORIGIN.y - float(pt.y))

    @staticmethod
    def _conv_vector(pt):
        return pcb.wxPoint(float(pt.x), -float(pt.y))

    @staticmethod
    def _conv_track(track, net_code):
        if len(track.points) < 2:
            return
        old_pt = track.points[0]
        for pt in track.points[1:]:
            t = pcb.TRACK(pcb.GetBoard())
            t.SetStart(ToPCB._conv_point(old_pt))
            t.SetEnd(ToPCB._conv_point(pt))
            t.SetNetCode(net_code)
            t.SetLayer(track.layer)
            # t.SetWidth(pcb.FromMM(DEFAULT_TRACK_WIDTH_MM))
            pcb.GetBoard().Add(t)
            old_pt = pt

    @staticmethod
    def _conv_via(via, net_code):
        v = pcb.VIA(pcb.GetBoard())
        v.SetPosition(ToPCB._conv_point(via.position))
        v.SetViaType(pcb.VIA_THROUGH)
        v.SetLayerPair(cad.Layer.F_Cu, cad.Layer.B_Cu)
        v.SetNetCode(net_code)
        # v.SetWidth(pcb.FromMM(DEFAULT_TRACK_WIDTH_MM))
        pcb.GetBoard().Add(v)

    @staticmethod
    def _conv_fill(fill, net_code):
        conv_pts = list(map(ToPCB._conv_point, fill.points))
        area = pcb.GetBoard().InsertArea(net_code, pcb.GetBoard().GetAreaCount(), fill.layer,
                                         conv_pts[0].x, conv_pts[0].y, pcb.CPolyLine.DIAGONAL_EDGE)
        area.SetPadConnection(pcb.PAD_ZONE_CONN_THERMAL if fill.thermal else pcb.PAD_ZONE_CONN_FULL)
        outline = area.Outline()
        for pt in conv_pts[1:]:
            if getattr(outline, 'AppendCorner', None) is None:
                # Kicad nightly
                outline.Append(pt.x, pt.y)
            else:
                outline.AppendCorner(pt.x, pt.y)
        if getattr(outline, 'CloseLastContour', None) is not None:
            outline.CloseLastContour()
        # area.SetCornerRadius(pcb.FromMM(DEFAULT_TRACK_WIDTH_MM / 2.))
        # area.SetCornerSmoothingType(pcb.ZONE_SETTINGS.SMOOTHING_FILLET)
        area.BuildFilledSolidAreasPolygons(pcb.GetBoard())

    @staticmethod
    def place_component(comp):
        modu = pcb.GetBoard().FindModule(comp.name)
        modu.SetPosition(ToPCB._conv_point(comp.position))
        modu.SetOrientation(ToPCB._conv_angle(comp.orientation))
        if modu.IsFlipped() != comp.flipped:
            modu.Flip()

    @staticmethod
    def apply(board):
        for comp in board.components.values():
            ToPCB.place_component(comp)
        to_delete = list(pcb.GetBoard().GetTracks())
        to_delete += list(map(pcb.GetBoard().GetArea, range(pcb.GetBoard().GetAreaCount())))
        for elm in to_delete:
            pcb.GetBoard().Delete(elm)
        for net in board.netlist.values():
            for trk in net.tracks:
                if isinstance(trk, cad.Track):
                    ToPCB._conv_track(trk, net.code)
                elif isinstance(trk, cad.Via):
                    ToPCB._conv_via(trk, net.code)
            for fill in net.fills:
                ToPCB._conv_fill(fill, net.code)

