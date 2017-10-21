from __future__ import unicode_literals
from illuminator import *
import math

import pcbnew


class Autoplacer(object):

    @classmethod
    def run(cls, *args, **kwargs):
        cls()(*args, **kwargs)

    def _get_modules(self):
        for mod in self.board.GetModules():
            self.modules[mod.GetReference().encode('utf-8')] = mod

    def place(self, name, place):
        mod = self.modules.get(name, None)
        if mod:
            mod.SetPosition(pcbnew.wxPointMM(place.x, place.y))
            mod.SetOrientation(-math.degrees(place.rot) * 10.)

    def __call__(self, *args, **kwargs):
        ill = Illuminator(*args, **kwargs)
        for name, place in ill():
            print('Placing %s at %s.' % (name, str(place)))
            self.place(name, place)

    def __init__(self):
        super(Autoplacer, self).__init__()
        self.board = pcbnew.GetBoard()
        self.modules = {}
        self._get_modules()
