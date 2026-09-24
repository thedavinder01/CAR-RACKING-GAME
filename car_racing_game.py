"""

"""
import math
import random
import sys

import pygame

# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------
W, H = 960, 600
FPS = 60

SEG_LEN = 200                 # length of one road segment (world units)
ROAD_W = 2000                 # half-width of the road in world units
LANES = 3
RUMBLE = 3                    # segments per stripe colour
DRAW_DIST = 180               # how many segments are drawn in 3D
FOV = 100
CAM_H = 1000
DEPTH = 1 / math.tan(math.radians(FOV / 2))
PLAYER_Z = CAM_H * DEPTH

MAX_SPEED = SEG_LEN * 60
ACCEL = MAX_SPEED / 5
BRAKE = -MAX_SPEED
DECEL = -MAX_SPEED / 5
OFFROAD_DECEL = -MAX_SPEED / 2
OFFROAD_LIMIT = MAX_SPEED / 4
CENTRIFUGAL = 0.3

START_TIME = 60
LAP_BONUS = 35
NUM_CARS = 48

SKY_TOP = (25, 80, 190)
SKY_BOTTOM = (175, 215, 250)
FOG = (175, 215, 250)

ROAD_COLORS = {
    False: dict(road=(107, 107, 107), grass=(16, 170, 16), rumble=(200, 30, 30), lane=(210, 210, 210)),
    True: dict(road=(100, 100, 100), grass=(0, 150, 0), rumble=(235, 235, 235), lane=None),
}
CAR_COLORS = [(30, 110, 230), (250, 200, 20), (40, 190, 90), (240, 240, 240),
              (150, 60, 210), (255, 140, 0), (20, 200, 200), (90, 90, 100)]


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def lerp(a, b, t):
    return a + (b - a) * t


def mix(c1, c2, t):
    return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))


def shade(c, f):
    return tuple(max(0, min(255, int(v * f))) for v in c)


def ease_in(a, b, p):
    return a + (b - a) * p * p


def ease_out(a, b, p):
    return a + (b - a) * (1 - (1 - p) ** 2)


def ease_in_out(a, b, p):
    return a + (b - a) * (-math.cos(p * math.pi) / 2 + 0.5)


# --------------------------------------------------------------------------
# Track
# --------------------------------------------------------------------------
class Point:
    __slots__ = ("wy", "wz", "cx", "cy", "cz", "sx", "sy", "sw", "scale")

    def __init__(self, wy, wz):
        self.wy, self.wz = wy, wz
        self.cx = self.cy = self.cz = 0.0
        self.sx = self.sy = self.sw = 0
        self.scale = 0.0


class Segment:
    def __init__(self, index, y1, y2, curve, dark):
        self.index = index
        self.p1 = Point(y1, index * SEG_LEN)
        self.p2 = Point(y2, (index + 1) * SEG_LEN)
        self.curve = curve
        self.dark = dark
        self.cars = []
        self.trees = []
        self.clip = H
        self.looped = False


def build_track():
    segs = []

    def last_y():
        return segs[-1].p2.wy if segs else 0

    def add_seg(curve, y):
        n = len(segs)
        segs.append(Segment(n, last_y(), y, curve, (n // RUMBLE) % 2 == 1))

    def road(enter, hold, leave, curve, hill):
        start_y = last_y()
        end_y = start_y + hill * SEG_LEN
        total = enter + hold + leave
        for n in range(enter):
            add_seg(ease_in(0, curve, n / enter), ease_in_out(start_y, end_y, n / total))
        for n in range(hold):
            add_seg(curve, ease_in_out(start_y, end_y, (enter + n) / total))
        for n in range(leave):
            add_seg(ease_out(curve, 0, n / leave), ease_in_out(start_y, end_y, (enter + hold + n) / total))

    road(25, 25, 25, 0, 0)
    road(50, 60, 50, 3, 12)
    road(40, 80, 40, -4, -8)
    road(60, 60, 60, 0, 20)
    road(40, 60, 40, 5, -14)
    road(50, 40, 50, -3, 0)
    road(40, 100, 40, 0, -10)
    road(60, 80, 60, 6, 10)
    road(50, 50, 50, -6, -8)
    road(60, 60, 60, 2, 0)
    road(50, 50, 50, 0, -last_y() / SEG_LEN)     # bring the track back to y = 0

    rng = random.Random(7)
    for seg in segs:
        if seg.index % 7 == 0:
            side = rng.choice((-1, 1))
            seg.trees.append(side * rng.uniform(1.5, 2.4))
        if seg.index % 19 == 0:
            seg.trees.append(-1 * rng.choice((-1, 1)) * rng.uniform(1.4, 2.0))
    return segs


class Car:
    def __init__(self, z, offset, speed, color):
        self.z, self.offset, self.speed, self.color = z, offset, speed, color
        self.prev_dz = 0.0


# --------------------------------------------------------------------------
# Drawing helpers
# --------------------------------------------------------------------------
def make_sky():
    surf = pygame.Surface((W, H // 2 + 2))
    for y in range(surf.get_height()):
        t = min(1.0, y / (H / 2))
        pygame.draw.line(surf, mix(SKY_TOP, SKY_BOTTOM, t ** 0.8), (0, y), (W, y))
    # sun with glow
    sun = (int(W * 0.72), 120)
    glow = pygame.Surface((300, 300), pygame.SRCALPHA)
    for r in range(150, 30, -10):
        pygame.draw.circle(glow, (255, 240, 170, int(6 + (150 - r) * 0.35)), (150, 150), r)
    surf.blit(glow, (sun[0] - 150, sun[1] - 150))
    pygame.draw.circle(surf, (255, 250, 210), sun, 34)
    return surf


def make_layer(color, base, amp, seed):
    rnd = random.Random(seed)
    ph = [rnd.uniform(0, 6.28) for _ in range(3)]
    width = W * 2
    surf = pygame.Surface((width, 200), pygame.SRCALPHA)
    pts = [(0, 200)]
    for x in range(0, width + 1, 8):
        a = x / width * 2 * math.pi
        h = (base + amp * (0.6 * math.sin(a * 2 + ph[0]) + 0.3 * math.sin(a * 5 + ph[1])
                           + 0.1 * math.sin(a * 11 + ph[2])))
        pts.append((x, 200 - h))
    pts.append((width, 200))
    pygame.draw.polygon(surf, color, pts)
    return surf


def draw_car_rear(surf, cx, by, w, color, braking=False, tilt=0.0, fog=0.0):
    """Car seen from behind (3D view). (cx, by) = bottom centre."""
    if w < 4:
        return
    h = w * 0.62
    c = mix(color, FOG, fog)
    dark = shade(c, 0.55)
    # shadow
    pygame.draw.ellipse(surf, mix((25, 60, 25), FOG, fog), (cx - w * 0.55, by - h * 0.10, w * 1.1, h * 0.22))
    # wheels
    ww, wh = w * 0.17, h * 0.42
    pygame.draw.rect(surf, (15, 15, 15), (cx - w / 2, by - wh, ww, wh), border_radius=int(max(1, ww * 0.3)))
    pygame.draw.rect(surf, (15, 15, 15), (cx + w / 2 - ww, by - wh, ww, wh), border_radius=int(max(1, ww * 0.3)))
    # lower body
    body = pygame.Rect(cx - w * 0.47, by - h * 0.66, w * 0.94, h * 0.46)
    pygame.draw.rect(surf, c, body, border_radius=int(max(1, w * 0.08)))
    # cabin
    tx = tilt * w * 0.06
    cab = [(cx - w * 0.40, by - h * 0.64), (cx + w * 0.40, by - h * 0.64),
           (cx + w * 0.29 + tx, by - h), (cx - w * 0.29 + tx, by - h)]
    pygame.draw.polygon(surf, shade(c, 0.85), cab)
    win = [(cx - w * 0.34, by - h * 0.67), (cx + w * 0.34, by - h * 0.67),
           (cx + w * 0.25 + tx, by - h * 0.94), (cx - w * 0.25 + tx, by - h * 0.94)]
    pygame.draw.polygon(surf, mix((25, 35, 55), FOG, fog), win)
    # spoiler
    pygame.draw.rect(surf, dark, (cx - w * 0.44, by - h * 0.72, w * 0.88, h * 0.07))
    # bumper
    pygame.draw.rect(surf, dark, (cx - w * 0.47, by - h * 0.28, w * 0.94, h * 0.12), border_radius=int(max(1, w * 0.03)))
    # tail lights + plate
    lc = (255, 60, 60) if braking else (170, 20, 20)
    lw, lh = w * 0.2, h * 0.11
    pygame.draw.rect(surf, lc, (cx - w * 0.44, by - h * 0.55, lw, lh))
    pygame.draw.rect(surf, lc, (cx + w * 0.44 - lw, by - h * 0.55, lw, lh))
    if braking:
        pygame.draw.rect(surf, (255, 200, 200), (cx - w * 0.30, by - h * 0.53, w * 0.60, h * 0.05))
    pygame.draw.rect(surf, (235, 235, 235), (cx - w * 0.12, by - h * 0.40, w * 0.24, h * 0.1))


def draw_tree(surf, cx, by, w, fog=0.0):
    if w < 5:
        return
    trunk = mix((100, 65, 30), FOG, fog)
    l1, l2 = mix((20, 110, 30), FOG, fog), mix((30, 145, 45), FOG, fog)
    pygame.draw.rect(surf, trunk, (cx - w * 0.06, by - w * 0.35, w * 0.12, w * 0.35))
    pygame.draw.polygon(surf, l1, [(cx - w * 0.38, by - w * 0.25), (cx + w * 0.38, by - w * 0.25), (cx, by - w * 0.85)])
    pygame.draw.polygon(surf, l2, [(cx - w * 0.30, by - w * 0.55), (cx + w * 0.30, by - w * 0.55), (cx, by - w * 1.15)])


def draw_car_top(surf, cx, cy, w, l, color, braking=False):
    """Car seen from above (2D view). (cx, cy) = centre."""
    body = pygame.Rect(0, 0, w, l)
    body.center = (cx, cy)
    pygame.draw.rect(surf, (10, 10, 10), (body.left - 4, body.top + l * 0.12, 6, l * 0.24), border_radius=2)
    pygame.draw.rect(surf, (10, 10, 10), (body.right - 2, body.top + l * 0.12, 6, l * 0.24), border_radius=2)
    pygame.draw.rect(surf, (10, 10, 10), (body.left - 4, body.bottom - l * 0.36, 6, l * 0.24), border_radius=2)
    pygame.draw.rect(surf, (10, 10, 10), (body.right - 2, body.bottom - l * 0.36, 6, l * 0.24), border_radius=2)
    pygame.draw.rect(surf, color, body, border_radius=10)
    pygame.draw.rect(surf, shade(color, 0.6), body, 2, border_radius=10)
    pygame.draw.polygon(surf, (30, 45, 70), [(cx - w * 0.36, cy - l * 0.10), (cx + w * 0.36, cy - l * 0.10),
                                             (cx + w * 0.30, cy - l * 0.30), (cx - w * 0.30, cy - l * 0.30)])
    pygame.draw.rect(surf, shade(color, 0.85), (cx - w * 0.32, cy - l * 0.08, w * 0.64, l * 0.30), border_radius=4)
    pygame.draw.polygon(surf, (30, 45, 70), [(cx - w * 0.30, cy + l * 0.24), (cx + w * 0.30, cy + l * 0.24),
                                             (cx + w * 0.26, cy + l * 0.32), (cx - w * 0.26, cy + l * 0.32)])
    pygame.draw.rect(surf, (255, 245, 170), (cx - w * 0.42, body.top + 2, w * 0.24, 6), border_radius=2)
    pygame.draw.rect(surf, (255, 245, 170), (cx + w * 0.18, body.top + 2, w * 0.24, 6), border_radius=2)
    lc = (255, 40, 40) if braking else (150, 20, 20)
    pygame.draw.rect(surf, lc, (cx - w * 0.42, body.bottom - 7, w * 0.24, 5), border_radius=2)
    pygame.draw.rect(surf, lc, (cx + w * 0.18, body.bottom - 7, w * 0.24, 5), border_radius=2)


# --------------------------------------------------------------------------
# Game
# --------------------------------------------------------------------------
class Game:
    def __init__(self, screen):
        self.screen = screen
        self.canvas = pygame.Surface((W, H))
        self.segments = build_track()
        self.N = len(self.segments)
        self.track_len = self.N * SEG_LEN
        self.sky = make_sky()
        self.layers = [make_layer((110, 140, 190, 255), 90, 55, 1),
                       make_layer((70, 110, 130, 255), 60, 40, 2),
                       make_layer((40, 100, 60, 255), 35, 25, 3)]
        self.font_s = pygame.font.SysFont("arial", 18, bold=True)
        self.font_m = pygame.font.SysFont("arial", 28, bold=True)
        self.font_l = pygame.font.SysFont("arial", 64, bold=True)
        self.state = "menu"
        self.view3d = True
        self.paused = False
        self.clock_t = 0.0
        self.reset()

    # ---------------- setup ----------------
    def reset(self):
        self.position = 0.0
        self.speed = 0.0
        self.player_x = 0.0
        self.steer = 0.0
        self.time_left = START_TIME
        self.lap = 1
        self.distance = 0.0
        self.passed = 0
        self.shake = 0.0
        self.hit_cd = 0.0
        self.msg, self.msg_t = "", 0.0
        self.bg = [0.0, 0.0, 0.0]
        self.braking = False
        for seg in self.segments:
            seg.cars = []
        self.cars = []
        lane_offsets = [-0.66, 0.0, 0.66]
        lane_speeds = [0.22, 0.30, 0.40]
        per_lane = NUM_CARS // 3
        spacing = self.track_len / per_lane
        for i in range(NUM_CARS):
            lane = i % 3
            z = (5000 + (i // 3) * spacing + random.uniform(0, spacing * 0.4)) % self.track_len
            car = Car(z, lane_offsets[lane], MAX_SPEED * lane_speeds[lane], random.choice(CAR_COLORS))
            self.cars.append(car)
            self.find(z).cars.append(car)

    def find(self, z):
        return self.segments[int(z // SEG_LEN) % self.N]

    def flash(self, text, t=2.0):
        self.msg, self.msg_t = text, t

    # ---------------- update ----------------
    def update(self, dt, keys):
        self.clock_t += dt
        if self.state == "menu":
            self.position = (self.position + MAX_SPEED * 0.5 * dt) % self.track_len
            self.speed = MAX_SPEED * 0.5
            self.bg[0] += self.find(self.position + PLAYER_Z).curve * 0.5 * dt * 60 * 0.6
            self.move_cars(dt)
            return
        if self.paused:
            return

        left = keys[pygame.K_LEFT] or keys[pygame.K_a]
        right = keys[pygame.K_RIGHT] or keys[pygame.K_d]
        up = keys[pygame.K_UP] or keys[pygame.K_w]
        down = keys[pygame.K_DOWN] or keys[pygame.K_s]

        over = self.state == "over"
        if over:
            up = left = right = False
            down = True

        pseg = self.find(self.position + PLAYER_Z)
        sp = self.speed / MAX_SPEED
        dx = dt * 2 * sp

        if left:
            self.player_x -= dx
        elif right:
            self.player_x += dx
        self.steer += ((right - left) - self.steer) * min(1.0, dt * 8)
        self.player_x -= dx * sp * pseg.curve * CENTRIFUGAL

        if up:
            self.speed += ACCEL * dt
        elif down:
            self.speed += BRAKE * dt
        else:
            self.speed += DECEL * dt
        self.braking = bool(down and self.speed > 0)

        if (self.player_x < -1 or self.player_x > 1):
            if self.speed > OFFROAD_LIMIT:
                self.speed += OFFROAD_DECEL * dt
            self.shake = max(self.shake, 0.25 * sp)
        self.player_x = max(-2.6, min(2.6, self.player_x))
        self.speed = max(0.0, min(self.speed, MAX_SPEED))

        old_pos = self.position
        self.position += self.speed * dt
        self.distance += self.speed * dt
        if self.position >= self.track_len:
            self.position -= self.track_len
        if self.position < old_pos and not over:
            self.lap += 1
            self.time_left += LAP_BONUS
            self.flash(f"LAP {self.lap}!   +{LAP_BONUS}s", 2.5)

        self.bg[0] += pseg.curve * sp * dt * 60 * 0.6
        self.bg[1] += pseg.curve * sp * dt * 60 * 1.2
        self.bg[2] += pseg.curve * sp * dt * 60 * 2.2

        self.move_cars(dt)

        # collisions & overtaking
        pz = (self.position + PLAYER_Z) % self.track_len
        self.hit_cd = max(0.0, self.hit_cd - dt)
        for car in self.cars:
            dz = (car.z - pz + self.track_len / 2) % self.track_len - self.track_len / 2
            if (-SEG_LEN * 0.6 < dz < SEG_LEN * 1.4 and abs(car.offset - self.player_x) < 0.36
                    and self.hit_cd <= 0 and not over):
                self.speed = min(self.speed, car.speed) * 0.55
                self.shake = 0.9
                self.hit_cd = 0.8
                self.time_left -= 2
                self.player_x += (1 if self.player_x >= car.offset else -1) * 0.18
                self.flash("CRASH!  -2s", 1.2)
            if car.prev_dz > 0 >= dz and abs(dz) < SEG_LEN * 8 and not over:
                self.passed += 1
            car.prev_dz = dz

        if not over:
            self.time_left -= dt
            if self.time_left <= 0:
                self.time_left = 0
                self.state = "over"
        self.shake = max(0.0, self.shake - dt * 1.6)
        self.msg_t = max(0.0, self.msg_t - dt)

    def move_cars(self, dt):
        for car in self.cars:
            old = self.find(car.z)
            car.z = (car.z + car.speed * dt) % self.track_len
            new = self.find(car.z)
            if old is not new:
                old.cars.remove(car)
                new.cars.append(car)

    # ---------------- 3D rendering ----------------
    def project(self, p, cam_x, cam_y, cam_z):
        p.cx = 0 - cam_x
        p.cy = p.wy - cam_y
        p.cz = p.wz - cam_z
        if p.cz < 1:
            p.cz = 1
        p.scale = DEPTH / p.cz
        p.sx = int(W / 2 + p.scale * p.cx * W / 2)
        p.sy = int(H / 2 - p.scale * p.cy * H / 2)
        p.sw = int(p.scale * ROAD_W * W / 2)

    def draw_background(self, c):
        c.blit(self.sky, (0, 0))
        horizon = H // 2
        for i, layer in enumerate(self.layers):
            off = int(self.bg[i]) % (W * 2)
            y = horizon - 200 + 30 - i * 6 + i * 14
            c.blit(layer, (-off, y))
            c.blit(layer, (-off + W * 2, y))
        pygame.draw.rect(c, mix((0, 150, 0), FOG, 0.75), (0, horizon + 22, W, H - horizon))

    def draw_3d(self):
        c = self.canvas
        self.draw_background(c)

        base = self.find(self.position)
        base_pct = (self.position % SEG_LEN) / SEG_LEN
        pz = self.position + PLAYER_Z
        pseg = self.find(pz)
        ppct = (pz % SEG_LEN) / SEG_LEN
        player_y = lerp(pseg.p1.wy, pseg.p2.wy, ppct)

        maxy = H
        x = 0.0
        dx = -(base.curve * base_pct)
        drawn = []
        for n in range(DRAW_DIST):
            seg = self.segments[(base.index + n) % self.N]
            seg.looped = seg.index < base.index
            cam_z = self.position - (self.track_len if seg.looped else 0)
            cx = self.player_x * ROAD_W
            self.project(seg.p1, cx - x, player_y + CAM_H, cam_z)
            self.project(seg.p2, cx - x - dx, player_y + CAM_H, cam_z)
            x += dx
            dx += seg.curve
            seg.clip = maxy
            drawn.append((n, seg))
            if seg.p1.cz <= DEPTH or seg.p2.sy >= seg.p1.sy or seg.p2.sy >= maxy:
                continue
            self.draw_segment(c, seg, n)
            maxy = seg.p1.sy

        # sprites (trees + traffic), far to near
        for n, seg in reversed(drawn):
            fog = min(0.8, (n / DRAW_DIST) ** 2)
            p1, p2 = seg.p1, seg.p2
            if p1.cz <= DEPTH:
                continue
            c.set_clip(pygame.Rect(0, 0, W, max(0, int(seg.clip))))
            for off in seg.trees:
                sx = p1.sx + p1.scale * off * ROAD_W * W / 2
                draw_tree(c, sx, p1.sy, p1.sw * 0.9, fog)
            for car in seg.cars:
                pct = (car.z % SEG_LEN) / SEG_LEN
                scale = lerp(p1.scale, p2.scale, pct)
                sx = lerp(p1.sx, p2.sx, pct) + scale * car.offset * ROAD_W * W / 2
                sy = lerp(p1.sy, p2.sy, pct)
                draw_car_rear(c, sx, sy, scale * ROAD_W * W / 2 * 0.42, car.color, fog=fog)
            c.set_clip(None)

        self.draw_speed_lines(c)
        # player car
        sp = self.speed / MAX_SPEED
        bounce = math.sin(self.clock_t * 40) * 1.5 * sp if abs(self.player_x) <= 1 else math.sin(self.clock_t * 60) * 4 * sp
        draw_car_rear(c, W / 2 + self.steer * 6, H - 22 + bounce, W * 0.19, (225, 30, 40),
                      braking=self.braking, tilt=self.steer)

    def draw_segment(self, c, seg, n):
        p1, p2 = seg.p1, seg.p2
        col = ROAD_COLORS[seg.dark]
        fog = min(0.75, (n / DRAW_DIST) ** 2.2)
        y1, y2 = p1.sy, p2.sy
        x1, x2, w1, w2 = p1.sx, p2.sx, p1.sw, p2.sw

        pygame.draw.rect(c, mix(col["grass"], FOG, fog), (0, y2, W, y1 - y2 + 1))
        r1, r2 = w1 / max(6, 2 * LANES), w2 / max(6, 2 * LANES)
        rc = mix(col["rumble"], FOG, fog)
        pygame.draw.polygon(c, rc, [(x1 - w1 - r1, y1), (x1 - w1, y1), (x2 - w2, y2), (x2 - w2 - r2, y2)])
        pygame.draw.polygon(c, rc, [(x1 + w1 + r1, y1), (x1 + w1, y1), (x2 + w2, y2), (x2 + w2 + r2, y2)])
        pygame.draw.polygon(c, mix(col["road"], FOG, fog), [(x1 - w1, y1), (x1 + w1, y1), (x2 + w2, y2), (x2 - w2, y2)])
        if col["lane"] and n < DRAW_DIST * 0.8:
            l1, l2 = w1 / max(32, 8 * LANES), w2 / max(32, 8 * LANES)
            lw1, lw2 = w1 * 2 / LANES, w2 * 2 / LANES
            lx1, lx2 = x1 - w1 + lw1, x2 - w2 + lw2
            lc = mix(col["lane"], FOG, fog)
            for _ in range(LANES - 1):
                pygame.draw.polygon(c, lc, [(lx1 - l1 / 2, y1), (lx1 + l1 / 2, y1), (lx2 + l2 / 2, y2), (lx2 - l2 / 2, y2)])
                lx1 += lw1
                lx2 += lw2

    def draw_speed_lines(self, c):
        sp = self.speed / MAX_SPEED
        if sp < 0.6:
            return
        amount = int((sp - 0.55) * 30)
        for _ in range(amount):
            ang = random.uniform(0, math.tau)
            r0 = random.uniform(W * 0.32, W * 0.5)
            r1 = r0 + random.uniform(30, 90) * sp
            cx, cy = W / 2, H * 0.55
            pygame.draw.line(c, (235, 240, 250),
                             (cx + math.cos(ang) * r0 * 1.2, cy + math.sin(ang) * r0 * 0.7),
                             (cx + math.cos(ang) * r1 * 1.2, cy + math.sin(ang) * r1 * 0.7), 1)

    # ---------------- 2D rendering ----------------
    def draw_2d(self):
        c = self.canvas
        SEGPX, PY, HALF, BACK = 11, H - 120, 175, 14
        K = int(PY / SEGPX) + 4
        pz = self.position + PLAYER_Z
        base = self.find(pz)
        pp = (pz % SEG_LEN) / SEG_LEN
        c.fill((16, 160, 16))

        centers = []
        x, dx = 0.0, -(base.curve * pp)
        for k in range(K + 2):
            centers.append(W / 2 + x / ROAD_W * HALF * 0.7)
            x += dx
            dx += self.segments[(base.index + k) % self.N].curve
        centers = [centers[0]] * BACK + centers          # index j = k + BACK

        for k in range(-BACK, K):
            seg = self.segments[(base.index + k) % self.N]
            col = ROAD_COLORS[seg.dark]
            ya = PY - (k - pp) * SEGPX
            yb = ya - SEGPX
            ca, cb = centers[k + BACK], centers[k + BACK + 1]
            pygame.draw.rect(c, col["grass"], (0, yb, W, SEGPX + 1))
            rw = 14
            pygame.draw.polygon(c, col["rumble"], [(ca - HALF - rw, ya), (ca - HALF, ya), (cb - HALF, yb), (cb - HALF - rw, yb)])
            pygame.draw.polygon(c, col["rumble"], [(ca + HALF + rw, ya), (ca + HALF, ya), (cb + HALF, yb), (cb + HALF + rw, yb)])
            pygame.draw.polygon(c, col["road"], [(ca - HALF, ya), (ca + HALF, ya), (cb + HALF, yb), (cb - HALF, yb)])
            if seg.dark:
                for lx in (-HALF / 3, HALF / 3):
                    pygame.draw.polygon(c, (215, 215, 215), [(ca + lx - 2, ya), (ca + lx + 2, ya), (cb + lx + 2, yb), (cb + lx - 2, yb)])
        for k in range(-BACK, K):
            seg = self.segments[(base.index + k) % self.N]
            ca, cb = centers[k + BACK], centers[k + BACK + 1]
            ty = PY - (k - pp) * SEGPX - SEGPX / 2
            for off in seg.trees:
                tx = (ca + cb) / 2 + off * HALF
                pygame.draw.circle(c, (10, 90, 20), (tx + 3, ty + 4), 17)
                pygame.draw.circle(c, (25, 135, 40), (tx, ty), 16)
                pygame.draw.circle(c, (50, 175, 65), (tx - 4, ty - 4), 8)

        def center_at(t):
            j = max(0, min(len(centers) - 2, int(t)))
            return lerp(centers[j], centers[j + 1], t - j)

        for car in self.cars:
            dz = (car.z - pz + self.track_len / 2) % self.track_len - self.track_len / 2
            k = dz / SEG_LEN
            y = PY - k * SEGPX
            if -60 < y < H + 60 and -BACK < k < K:
                cx = center_at(k + pp + BACK) + car.offset * HALF
                draw_car_top(c, cx, y, HALF * 0.40, 76, car.color)

        px = W / 2 + self.player_x * HALF
        pygame.draw.ellipse(c, (70, 70, 70), (px - 34, PY - 36, 68, 86))
        draw_car_top(c, px + self.steer * 2, PY, HALF * 0.40, 78, (225, 30, 40), self.braking)
        if self.speed > MAX_SPEED * 0.6:
            for i in range(3):
                pygame.draw.line(c, (255, 190, 60), (px - 8 + i * 8, PY + 42), (px - 8 + i * 8, PY + 42 + random.randint(8, 22)), 3)

    # ---------------- HUD ----------------
    def text(self, surf, font, msg, pos, color=(255, 255, 255), center=False):
        s = font.render(msg, True, color)
        sh = font.render(msg, True, (0, 0, 0))
        r = s.get_rect()
        if center:
            r.center = pos
        else:
            r.topleft = pos
        surf.blit(sh, (r.x + 2, r.y + 2))
        surf.blit(s, r)

    def draw_gauge(self, surf):
        cx, cy, r = W - 100, H - 72, 62
        sp = self.speed / MAX_SPEED
        pygame.draw.circle(surf, (14, 14, 24), (cx, cy), r + 6)
        pygame.draw.circle(surf, (90, 90, 120), (cx, cy), r + 6, 3)
        for i in range(12):
            a = math.radians(225 - i * 270 / 11)
            r0 = r - (10 if i % 2 == 0 else 6)
            pygame.draw.line(surf, (200, 200, 220) if i < 9 else (255, 80, 80),
                             (cx + math.cos(a) * r0, cy - math.sin(a) * r0),
                             (cx + math.cos(a) * (r - 2), cy - math.sin(a) * (r - 2)), 2)
        a = math.radians(225 - sp * 270)
        pygame.draw.line(surf, (255, 70, 70), (cx, cy), (cx + math.cos(a) * (r - 14), cy - math.sin(a) * (r - 14)), 4)
        pygame.draw.circle(surf, (230, 230, 230), (cx, cy), 6)
        self.text(surf, self.font_m, str(int(sp * 240)), (cx, cy + 30), center=True)
        self.text(surf, self.font_s, "km/h", (cx, cy + 50), (180, 180, 200), center=True)

    def draw_hud(self, surf):
        panel = pygame.Surface((W, 54), pygame.SRCALPHA)
        panel.fill((0, 0, 0, 120))
        surf.blit(panel, (0, 0))
        tcol = (255, 80, 80) if self.time_left < 10 else (255, 255, 255)
        self.text(surf, self.font_m, f"TIME  {int(self.time_left):02d}", (W / 2, 27), tcol, center=True)
        self.text(surf, self.font_s, f"LAP {self.lap}", (18, 8))
        self.text(surf, self.font_s, f"DIST {self.distance / 100:,.0f} m", (18, 30))
        self.text(surf, self.font_s, f"OVERTAKES {self.passed}", (W - 190, 8))
        self.text(surf, self.font_s, "VIEW: " + ("3D" if self.view3d else "2D") + "  [V]", (W - 190, 30))
        self.draw_gauge(surf)
        if self.msg_t > 0:
            self.text(surf, self.font_l, self.msg, (W / 2, 150), (255, 230, 80), center=True)

    def overlay(self, surf, lines):
        dim = pygame.Surface((W, H), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 150))
        surf.blit(dim, (0, 0))
        for text, font, color, y in lines:
            self.text(surf, font, text, (W / 2, y), color, center=True)

    # ---------------- main draw ----------------
    def draw(self):
        if self.view3d or self.state == "menu":
            self.draw_3d()
        else:
            self.draw_2d()

        self.screen.fill((0, 0, 0))
        ox = oy = 0
        if self.shake > 0:
            ox = random.randint(-1, 1) * int(self.shake * 8)
            oy = random.randint(-1, 1) * int(self.shake * 8)
        self.screen.blit(self.canvas, (ox, oy))

        if self.state == "menu":
            self.overlay(self.screen, [
                ("TURBO RACER", self.font_l, (255, 220, 60), 130),
                ("2D  +  3D  Car Racing", self.font_m, (255, 255, 255), 190),
                ("UP / W  accelerate      DOWN / S  brake", self.font_s, (220, 220, 240), 270),
                ("LEFT / RIGHT or A / D  steer", self.font_s, (220, 220, 240), 300),
                ("V  switch 2D / 3D view      P  pause", self.font_s, (220, 220, 240), 330),
                ("Beat the clock - every lap gives bonus time!", self.font_s, (255, 200, 120), 375),
                ("Press ENTER or SPACE to start", self.font_m, (120, 255, 150) if int(self.clock_t * 2) % 2 else (255, 255, 255), 450),
            ])
            return
        self.draw_hud(self.screen)
        if self.paused:
            self.overlay(self.screen, [("PAUSED", self.font_l, (255, 255, 255), H / 2)])
        elif self.state == "over":
            self.overlay(self.screen, [
                ("TIME UP!", self.font_l, (255, 90, 90), 170),
                (f"Distance: {self.distance / 100:,.0f} m", self.font_m, (255, 255, 255), 250),
                (f"Laps: {self.lap}     Overtakes: {self.passed}", self.font_m, (255, 255, 255), 292),
                (f"Score: {int(self.distance / 100 + self.passed * 50):,}", self.font_l, (255, 220, 60), 370),
                ("Press R to race again", self.font_m, (120, 255, 150), 460),
            ])


# --------------------------------------------------------------------------
def main():
    pygame.init()
    pygame.display.set_caption("Turbo Racer - 2D + 3D Car Racing")
    screen = pygame.display.set_mode((W, H))
    clock = pygame.time.Clock()
    game = Game(screen)

    while True:
        dt = min(clock.tick(FPS) / 1000.0, 0.05)
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    pygame.quit()
                    sys.exit()
                elif e.key in (pygame.K_RETURN, pygame.K_SPACE) and game.state == "menu":
                    game.reset()
                    game.state = "play"
                elif e.key == pygame.K_v:
                    game.view3d = not game.view3d
                elif e.key == pygame.K_p and game.state == "play":
                    game.paused = not game.paused
                elif e.key == pygame.K_r and game.state != "menu":
                    game.reset()
                    game.state = "play"
                    game.paused = False
        game.update(dt, pygame.key.get_pressed())
        game.draw()
        pygame.display.flip()


if __name__ == "__main__":
    main()
