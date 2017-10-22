from __future__ import unicode_literals
from collections import namedtuple
import math


Place = namedtuple('Place', ['x', 'y', 'rot'])


def ortho(a):
    return a - math.pi / 2.

def to_cartesian(c, angle, r):
    return c.__class__(c.x + r * math.cos(angle), c.y + r * math.sin(angle))

def to_polar(c, pos):
    pos_dx = pos.x - c.x
    pos_dy = pos.y - c.y
    r = math.sqrt(pos_dx * pos_dx + pos_dy * pos_dy)
    angle = math.acos(pos_dx / r)
    if pos_dy < 0.: angle = 2. * math.pi - angle
    return (angle, r)

def shift_along_radius(c, pos, shift):
    delta = pos - c
    radius = math.sqrt(delta.x * delta.x + delta.y * delta.y)
    scale_factor = float(shift) / radius
    return pos + pos.__class__(delta.x * scale_factor, delta.y * scale_factor)

def shift_along_arc(c, pos, delta_angle):
    angle, r = to_polar(c, pos)
    return to_cartesian(c, angle + delta_angle, r)

def compute_radial_segment(c, start, end=None, angle=None, steps=None, angular_resolution=None, excess_angle=0., skip_start=True):
    assert((end is None) != (angle is None))
    # Determine polar coordinates of start
    start_angle, start_r = to_polar(c, start)

    if end is None:
        end_r = start_r
        end_angle = start_angle + angle
    else:
        end_angle, end_r = to_polar(c, end)

    # Choose the arc < 180 degrees
    if abs(end_angle - start_angle) > math.pi:
        if start_angle < end_angle:
            end_angle -= 2. * math.pi
        else:
            start_angle -= 2. * math.pi
    assert((steps is None) != (angular_resolution is None))
    if steps is None:
        steps = int(math.ceil(abs(end_angle - start_angle) / angular_resolution))
    if excess_angle != 0.:
        if start_angle <= end_angle:
            start_angle -= excess_angle
            end_angle += excess_angle
        else:
            start_angle += excess_angle
            end_angle -= excess_angle
    for i in range(steps + 1):
        frac = float(i) / float(steps)
        angle = start_angle + frac * (end_angle - start_angle)
        r = start_r + frac * (end_r - start_r)
        if i > 0 or not skip_start:
            yield to_cartesian(c, angle, r)


class RadialPlacer(object):

    def get_resistor_name(self, line_idx):
        return '%s%d' % (self.resistor_prefix, line_idx)

    def get_led_name(self, line_idx, led_idx):
        return '%s%d' % (self.led_prefix, line_idx * self.n_leds_per_line + led_idx)

    def get_one_place(self, angle, orientation=0.):
        return Place(
            x=self.center.x + self.radius * math.cos(angle + self.center.rot),
            y=self.center.y + self.radius * math.sin(angle + self.center.rot),
            rot=ortho(angle + self.center.rot) + orientation
        )

    def __call__(self):
        # Total number of elements
        n_elm = self.n_lines * (1 + self.n_leds_per_line)
        angle_step = 2. * math.pi / float(n_elm)
        angle = 0.
        for line_idx in range(self.n_lines):
            yield (self.get_resistor_name(line_idx),
                self.get_one_place(angle, orientation=self.resistor_orientation))
            angle -= angle_step
            for led_idx in range(self.n_leds_per_line):
                yield (self.get_led_name(line_idx, led_idx),
                    self.get_one_place(angle, orientation=self.led_orientation))
                angle -= angle_step

    def __init__(self,
                n_lines=3,
                n_leds_per_line=3,
                radius=1.,
                center=Place(x=0., y=0., rot=0.),
                led_orientation=math.pi,
                resistor_orientation=0.,
                led_prefix='LED',
                resistor_prefix='R'
            ):
        super(RadialPlacer, self).__init__()
        self.n_leds_per_line = n_leds_per_line
        self.n_lines = n_lines
        self.center = center
        self.radius = radius
        self.led_orientation = led_orientation
        self.resistor_orientation = resistor_orientation
        self.led_prefix = led_prefix
        self.resistor_prefix = resistor_prefix


if __name__ == '__main__':
    ill = RadialPlacer()
    for k, v in ill():
        print(k, v)
