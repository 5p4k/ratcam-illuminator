from __future__ import unicode_literals
from collections import namedtuple
import math


Place = namedtuple('Place', ['x', 'y', 'rot'])


def ortho(a):
    return a - math.pi / 2.

def compute_radial_segment(c, start, end=None, angle=None, steps=None, angular_resolution=None):
    assert((end is None) != (angle is None))
    # Determine polar coordinates of start
    start_dx = start.x - c.x
    start_dy = start.y - c.y
    start_r = math.sqrt(start_dx * start_dx + start_dy * start_dy)
    start_angle = math.acos(start_dx / start_r)
    if start_dy < 0.: start_angle = 2. * math.pi - start_angle

    if end is None:
        end_r = start_r
        end_angle = start_angle + angle
    else:
        end_dx = end.x - c.x
        end_dy = end.y - c.y
        end_r = math.sqrt(end_dx * end_dx + end_dy * end_dy)
        end_angle = math.acos(end_dx / end_r)
        if end_dy < 0.: end_angle = 2. * math.pi - end_angle

    # Choose the arc < 180 degrees
    if abs(end_angle - start_angle) > math.pi:
        if start_angle < end_angle:
            end_angle -= 2. * math.pi
        else:
            start_angle -= 2. * math.pi
    assert((steps is None) != (angular_resolution is None))
    if steps is None:
        steps = int(math.ceil(abs(end_angle - start_angle) / angular_resolution))
    for i in range(steps):
        frac = float(1 + i) / float(steps)
        angle = start_angle + frac * (end_angle - start_angle)
        r = start_r + frac * (end_r - start_r)
        x = c.x + r * math.cos(angle)
        y = c.y + r * math.sin(angle)
        yield (x, y)


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

    def print_settings(self):
        print('Settings:')
        print('n_leds_per_line: %s' % str(self.n_leds_per_line))
        print('n_lines: %s' % str(self.n_lines))
        print('center: %s' % str(self.center))
        print('radius: %s' % str(self.radius))
        print('led_orientation: %s' % str(self.led_orientation))
        print('led_prefix: %s' % str(self.led_prefix))
        print('resistor_prefix: %s' % str(self.resistor_prefix))


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
