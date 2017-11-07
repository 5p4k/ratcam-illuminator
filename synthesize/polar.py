from __future__ import print_function, unicode_literals
import math


class Vector(object):
    def __add__(self, other):
        if isinstance(other, Vector):
            return Vector(self.dx + other.dx, self.dy + other.dy)
        elif isinstance(other, Point):
            return Point(other.x + self.dx, other.y + self.dy)
        else:
            raise TypeError()

    def __radd__(self, other):
        if isinstance(other, Vector):
            return Vector(self.dx + other.dx, self.dy + other.dy)
        elif isinstance(other, Point):
            return Point(other.x + self.dx, other.y + self.dy)
        else:
            raise TypeError()

    def __sub__(self, other):
        if isinstance(other, Vector):
            return Vector(self.dx - other.dx, self.dy - other.dy)
        elif isinstance(other, Point):
            return Point(self.dx - other.x, self.dy - other.y)
        else:
            raise TypeError()

    def __mul__(self, other):
        if not isinstance(other, float) or isinstance(other, int):
            raise TypeError()
        return Vector(float(other) * self.dx, float(other) * self.dy)

    def __div__(self, other):
        if not isinstance(other, float) or isinstance(other, int):
            raise TypeError()
        return Vector(self.dx / float(other), self.dy / float(other))

    def __repr__(self):
        return 'Vector(%f, %f)' % (self.dx, self.dy)

    def __str__(self):
        return repr(self)

    def l2(self):
        return math.sqrt(self.dx * self.dx + self.dy * self.dy)

    def l1(self):
        return abs(self.dx) + abs(self.dy)

    def normalized(self):
        return self / self.l2()

    def to_point(self):
        return Point(self.dx, self.dy)

    def to_polar(self):
        norm = self.l2()
        if self.dx == self.dy == 0.:
            return Polar(float('NaN'), 0.)
        a = math.acos(self.dx / self.l2())
        return Polar(a if self.dy >= 0. else 2. * math.pi - a, norm)

    def change(self, **kwargs):
        retval = Vector(self.dx, self.dy)
        for k, v in kwargs.items():
            setattr(retval, k, v)
        return retval

    def rotated(self, angle):
        pol = self.to_polar()
        pol.a += angle
        return pol.to_point().to_vector()

    def flipped(self, flip_x=False, flip_y=False):
        return Vector(-self.dx if flip_x else self.dx, -self.dy if flip_y else self.dy)

    def __init__(self, dx=0., dy=0.):
        self.dx = dx
        self.dy = dy


class Point(object):
    def __add__(self, other):
        if not isinstance(other, Vector):
            raise TypeError()
        return Point(self.x + other.dx, self.y + other.dy)

    def __radd__(self, other):
        if not isinstance(other, Vector):
            raise TypeError()
        return Point(self.x + other.dx, self.y + other.dy)

    def __sub__(self, other):
        if isinstance(other, Vector):
            return Point(self.x - other.dx, self.y - other.dy)
        elif isinstance(other, Point):
            return Vector(self.x - other.x, self.y - other.y)
        else:
            raise TypeError()

    def __mul__(self, other):
        if not isinstance(other, float) or isinstance(other, int):
            raise TypeError()
        return Point(float(other) * self.x, float(other) * self.y)

    def __div__(self, other):
        if not isinstance(other, float) or isinstance(other, int):
            raise TypeError()
        return Point(self.x / float(other), self.y / float(other))

    def __eq__(self, other):
        if not isinstance(other, Point):
            raise TypeError()
        return self.x == other.x and self.y == other.y

    def __ne__(self, other):
        if not isinstance(other, Point):
            raise TypeError()
        return self.x != other.x or self.y != other.y

    def __repr__(self):
        return 'Point(%f, %f)' % (self.x, self.y)

    def __str__(self):
        return repr(self)

    def change(self, **kwargs):
        retval = Point(self.x, self.y)
        for k, v in kwargs.items():
            setattr(retval, k, v)
        return retval

    def to_vector(self):
        return Vector(self.x, self.y)

    def to_polar(self):
        return self.to_vector().to_polar()

    def __init__(self, x=0., y=0.):
        self.x = x
        self.y = y


class Polar(object):
    def to_point(self):
        return Point(math.cos(self.a) * self.r, math.sin(self.a) * self.r)

    def angle_to(self, other):
        if not isinstance(other, Polar):
            raise TypeError()
        self._normalize()
        other._normalize()
        delta = other.a - self.a
        # Always return the shortest
        if delta < -math.pi:
            return delta + 2. * math.pi
        elif delta > math.pi:
            return delta - 2. * math.pi
        else:
            return delta

    def shift_along_tangent(self, shift, maintain_radius=True):
        if maintain_radius:
            chord = Chord(self.r, 0., self.a).with_length(2. * abs(shift))
        else:
            chord = Chord.from_length_and_distance(self.r, 2. * abs(shift), self.a)
        return chord.endpoints[0 if shift >= 0 else 1]

    def change(self, **kwargs):
        retval = Polar(self.a, self.r)
        for k, v in kwargs.items():
            setattr(retval, k, v)
        return retval

    def __eq__(self, other):
        if not isinstance(other, Polar):
            raise TypeError()
        self._normalize()
        other._normalize()
        return self.a == other.a and self.r == other.r

    def __ne__(self, other):
        if not isinstance(other, Polar):
            raise TypeError()
        self._normalize()
        other._normalize()
        return self.a != other.a or self.r != other.r

    def __repr__(self):
        return 'Polar(%f, %f)' % (self.a, self.r)

    def __str__(self):
        return repr(self)

    def _normalize(self):
        if self.r < 0.:
            self.a += math.pi
            self.r = -self.r
        self.a = normalize_angle(self.a)

    def __init__(self, a=0., r=0.):
        self.a = a
        self.r = r


class Chord(object):
    @property
    def aperture(self):
        return 2. * self._half_aperture

    @aperture.setter
    def aperture(self, x):
        self._half_aperture = x / 2.

    @property
    def distance_to_origin(self):
        return abs(math.cos(self._half_aperture)) * self.radius

    @property
    def length(self):
        return 2. * abs(math.sin(self._half_aperture)) * self.radius

    @property
    def center(self):
        return Polar(self.declination, self.distance_to_origin())

    @property
    def endpoints(self):
        return (Polar(self.declination - self._half_aperture, self.radius),
                Polar(self.declination + self._half_aperture, self.radius))

    def with_length(self, length):
        return Chord(self.radius, 2. * abs(math.asin(length / (2. * self.radius))), self.declination)

    def with_radius(self, radius):
        return Chord(radius, 0., self.declination).with_length(self.length)

    def with_distance_to_origin(self, distance):
        return self.with_radius(Vector(distance, self.length / 2.).l2())

    def change(self, **kwargs):
        retval = Chord(self.radius, self.aperture, self.declination)
        for k, v in kwargs.items():
            setattr(retval, k, v)
        return retval

    @classmethod
    def from_length_and_distance(cls, distance, length, declination=0.):
        return Chord(Vector(distance, float(length) / 2.).l2(), 0., declination).with_length(length)

    def __repr__(self):
        return 'Chord(%f, %f, %f)' % (self.radius, self.aperture, self.declination)

    def __str__(self):
        return repr(self)

    def __init__(self, radius=0., aperture=0., declination=0.):
        self.radius = radius
        self._half_aperture = aperture / 2.
        self.declination = declination


def apx_unit_interval(skip_start=False, include_end=False, resolution=None, steps=None):
    if resolution is not None:
        if resolution <= 0.:
            raise ValueError()
        steps = int(math.ceil(abs(1. / resolution)))
    if steps < 0:
        raise ValueError()
    elif steps == 0:
        return
    for i in range(1 if skip_start else 0, steps):
        yield float(i) / float(steps)
    if include_end:
        yield 1.


def apx_arc_through_polars(p1, p2, resolution=math.pi/60., steps=None, **kwargs):
    if not (isinstance(p1, Polar) and isinstance(p2, Polar)):
        raise TypeError()
    dr = p2.r - p1.r
    da = p1.angle_to(p2)
    if steps is None and resolution is not None and abs(da) > math.pi / 3600.:
        steps = int(math.ceil(abs(da / resolution)))
        resolution = None
    for x in apx_unit_interval(steps=steps, resolution=resolution, **kwargs):
        yield Polar(p1.a + x * da, p1.r + x * dr)


def apx_arc(p, da, resolution=math.pi/60., steps=None, **kwargs):
    if not isinstance(p, Polar):
        raise TypeError()
    if steps is None and resolution is not None and abs(da) > math.pi / 3600.:
        steps = int(math.ceil(abs(da / resolution)))
        resolution = None
    for x in apx_unit_interval(steps=steps, resolution=resolution, **kwargs):
        yield Polar(p.a + x * da, p.r)


def normalize_angle(a):
    a = math.fmod(a, 2. * math.pi)
    return a if a >= 0. else a + 2. * math.pi


def apx_crown_sector(a1, a2, inner_r, outer_r, shift1=0., shift2=0., **kwargs):
    # Compute the inner and outer polar points
    inner = [Polar(a1, inner_r), Polar(a2, inner_r)]
    outer = [Polar(a1, outer_r), Polar(a2, outer_r)]
    # Apply the shifts
    if shift1 != 0.:
        inner[0] = inner[0].shift_along_tangent(shift1, True)
        outer[0] = outer[0].shift_along_tangent(shift1, True)
    if shift2 != 0.:
        inner[1] = inner[1].shift_along_tangent(shift2, True)
        outer[1] = outer[1].shift_along_tangent(shift2, True)
    assert(inner[0].r == inner[1].r == inner_r)
    assert(outer[0].r == outer[1].r == outer_r)
    kwargs['skip_start'] = False
    kwargs['include_end'] = True
    for x in apx_arc_through_polars(inner[0], inner[1], **kwargs):
        yield x  # yield from would be handy
    for x in apx_arc_through_polars(outer[1], outer[0], **kwargs):
        yield x  # Another fake yield from
