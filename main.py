import array
import math
import random
import sys
from dataclasses import dataclass, field
from typing import Optional
import pygame

WIDTH = 1280
HEIGHT = 720
FPS = 60
STRIKE_ZONE = pygame.Rect(490, 252, 300, 270)
ZONE_CENTER = pygame.Vector2(STRIKE_ZONE.center)
PCI_LIMIT = STRIKE_ZONE.inflate(190, 170)
PLATE_SCREEN = pygame.Vector2(WIDTH / 2, 662)
FIELD_SCALE = 1.34
WALL_DISTANCE = 392.0
WALL_HEIGHT = 9.0
GRAVITY = 32.0
MPH_TO_FPS = 1.46667
MAX_INNINGS = 9


def clamp(value, low, high):
    return max(low, min(high, value))


def lerp(a, b, t):
    return a + (b - a) * t


def smoothstep(t):
    t = clamp(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def norm_to_zone(x_norm, y_norm):
    x = ZONE_CENTER.x + x_norm * STRIKE_ZONE.width * 0.5
    y = ZONE_CENTER.y - y_norm * STRIKE_ZONE.height * 0.5
    return pygame.Vector2(x, y)


def zone_to_norm(pos):
    return pygame.Vector2(
        (pos.x - ZONE_CENTER.x) / (STRIKE_ZONE.width * 0.5),
        (ZONE_CENTER.y - pos.y) / (STRIKE_ZONE.height * 0.5),
    )


def world_to_screen(x, y, z=0.0):
    return pygame.Vector2(
        PLATE_SCREEN.x + x * FIELD_SCALE,
        PLATE_SCREEN.y - y * FIELD_SCALE - z * 0.86,
    )


def fair_at(x, y):
    if y < 18:
        return True
    return abs(x) <= y * 1.02 + 8


def distance_ft(x, y):
    return math.hypot(x, y)


@dataclass(frozen=True)
class PitchSpec:
    name: str
    min_speed: int
    max_speed: int
    horizontal_break: float
    vertical_break: float
    difficulty: float
    color: tuple[int, int, int]


PITCH_SPECS = [
    PitchSpec("Fastball",  94, 101,   6.0,   2.0, 0.96, (245, 247, 255)),
    PitchSpec("Slider",    83,  90, -42.0,  -8.0, 0.82, (255, 229, 181)),
    PitchSpec("Curveball", 76,  83,  12.0, -54.0, 0.78, (208, 228, 255)),
    PitchSpec("Changeup",  78,  86,   9.0, -28.0, 0.86, (231, 255, 214)),
    PitchSpec("Sinker",    90,  96,  14.0, -36.0, 0.88, (255, 232, 220)),
    PitchSpec("Cutter",    88,  94, -18.0,  -4.0, 0.90, (255, 210, 255)),
    PitchSpec("Splitter",  84,  89,   4.0, -44.0, 0.80, (200, 245, 230)),
]

PITCH_WEIGHTS = [28, 18, 13, 15, 14, 7, 5]

SWING_TYPES = {
    "normal":  {"label": "Normal",  "pci": 76.0, "power": 1.00, "timing": 1.00, "contact": 1.00},
    "power":   {"label": "Power",   "pci": 58.0, "power": 1.14, "timing": 0.84, "contact": 0.86},
    "contact": {"label": "Contact", "pci": 94.0, "power": 0.86, "timing": 1.17, "contact": 1.20},
}

TIMING_COLORS = {
    "Perfect Timing": (255, 236, 120),
    "Good Timing":    (104, 230, 154),
    "Early":          (255, 184,  96),
    "Very Early":     (255, 111,  90),
    "Late":           (111, 191, 255),
    "Very Late":      ( 96, 125, 255),
    "No Swing":       (215, 219, 229),
    "Miss":           (255, 105, 105),
}

# Timing quality -> float for bar
TIMING_QUALITY = {
    "Perfect Timing": 1.00,
    "Good Timing":    0.75,
    "Early":          0.45,
    "Late":           0.45,
    "Very Early":     0.15,
    "Very Late":      0.15,
    "Miss":           0.00,
    "No Swing":       0.00,
}


# ─── Particle System ──────────────────────────────────────────────────────────
class Particle:
    def __init__(self, x, y, color, vx, vy, life, radius=4):
        self.x = x
        self.y = y
        self.color = color
        self.vx = vx
        self.vy = vy
        self.life = life
        self.max_life = life
        self.radius = radius

    def update(self, dt):
        self.vy += 420 * dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.life -= dt
        return self.life > 0

    def draw(self, screen):
        alpha_ratio = self.life / self.max_life
        r = int(clamp(self.color[0], 0, 255))
        g = int(clamp(self.color[1], 0, 255))
        b = int(clamp(self.color[2], 0, 255))
        rad = max(1, int(self.radius * alpha_ratio))
        pygame.draw.circle(screen, (r, g, b), (int(self.x), int(self.y)), rad)


class ParticleSystem:
    def __init__(self):
        self.particles: list[Particle] = []

    def emit_homerun(self, cx, cy):
        colors = [(255,220,60),(255,100,100),(120,220,255),(180,255,140),(255,180,255)]
        for _ in range(120):
            angle = random.uniform(0, math.tau)
            speed = random.uniform(120, 540)
            color = random.choice(colors)
            self.particles.append(Particle(
                cx + random.uniform(-20,20), cy + random.uniform(-20,20),
                color,
                math.cos(angle)*speed, math.sin(angle)*speed - 200,
                random.uniform(1.2, 2.4),
                random.randint(4, 9),
            ))

    def emit_hit(self, cx, cy, quality):
        for _ in range(int(18 + quality * 22)):
            angle = random.uniform(-math.pi, 0)
            speed = random.uniform(80, 280) * quality
            self.particles.append(Particle(
                cx, cy,
                (255, int(200*quality), 80),
                math.cos(angle)*speed, math.sin(angle)*speed,
                random.uniform(0.3, 0.9),
                random.randint(2, 5),
            ))

    def emit_strike(self, cx, cy):
        for _ in range(14):
            angle = random.uniform(0, math.tau)
            speed = random.uniform(40, 120)
            self.particles.append(Particle(
                cx, cy, (255, 90, 90),
                math.cos(angle)*speed, math.sin(angle)*speed,
                random.uniform(0.25, 0.6), 3,
            ))

    def update(self, dt):
        self.particles = [p for p in self.particles if p.update(dt)]

    def draw(self, screen):
        for p in self.particles:
            p.draw(screen)


# ─── Stats ────────────────────────────────────────────────────────────────────
@dataclass
class BattingStats:
    plate_appearances: int = 0
    at_bats: int = 0
    hits: int = 0
    singles: int = 0
    doubles: int = 0
    triples: int = 0
    home_runs: int = 0
    rbi: int = 0
    walks: int = 0
    strikeouts: int = 0
    total_exit_velo: float = 0.0
    hit_count_for_ev: int = 0
    max_exit_velo: float = 0.0
    max_distance: float = 0.0

    @property
    def avg(self):
        return self.hits / self.at_bats if self.at_bats else 0.0

    @property
    def slugging(self):
        total_bases = self.singles + 2*self.doubles + 3*self.triples + 4*self.home_runs
        return total_bases / self.at_bats if self.at_bats else 0.0

    @property
    def obp(self):
        num = self.hits + self.walks
        denom = self.at_bats + self.walks
        return num / denom if denom else 0.0

    @property
    def avg_exit_velo(self):
        return self.total_exit_velo / self.hit_count_for_ev if self.hit_count_for_ev else 0.0


# ─── Sound ────────────────────────────────────────────────────────────────────
class SoundManager:
    def __init__(self):
        self.enabled = False
        self.sounds = {}
        self.crowd_channel = None
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=44100, size=-16, channels=1, buffer=512)
            self.enabled = True
            self.crowd_channel = pygame.mixer.Channel(7)
            self._build_sounds()
            self.sounds["crowd"].set_volume(0.18)
            self.crowd_channel.play(self.sounds["crowd"], loops=-1)
        except pygame.error:
            self.enabled = False

    def play(self, name, volume=1.0):
        if not self.enabled or name not in self.sounds:
            return
        sound = self.sounds[name]
        sound.set_volume(volume)
        sound.play()

    def crowd_surge(self, volume=0.45):
        if self.enabled and self.crowd_channel:
            self.crowd_channel.set_volume(volume)
            pygame.time.set_timer(pygame.USEREVENT + 1, 1800, loops=1)

    def crowd_normal(self):
        if self.enabled and self.crowd_channel:
            self.crowd_channel.set_volume(0.18)

    def _tone(self, seconds, freq_a, freq_b=None, volume=0.45, noise=0.0, pulse=0.0):
        sample_rate = 44100
        total = max(1, int(seconds * sample_rate))
        freq_b = freq_a if freq_b is None else freq_b
        data = array.array("h")
        phase = 0.0
        for i in range(total):
            t = i / total
            freq = lerp(freq_a, freq_b, t)
            phase += (2.0 * math.pi * freq) / sample_rate
            env = (1.0 - t) ** 1.85
            if pulse:
                env *= 0.65 + 0.35 * math.sin(t * math.pi * pulse) ** 2
            value = math.sin(phase) * env
            if noise:
                value += random.uniform(-1.0, 1.0) * noise * env
            data.append(int(clamp(value * volume, -1.0, 1.0) * 32767))
        return pygame.mixer.Sound(buffer=data.tobytes())

    def _crowd(self):
        sample_rate = 44100
        seconds = 3.2
        total = int(seconds * sample_rate)
        data = array.array("h")
        phase_a = 0.0
        phase_b = 0.0
        for i in range(total):
            t = i / sample_rate
            phase_a += 2.0 * math.pi * 115.0 / sample_rate
            phase_b += 2.0 * math.pi * 167.0 / sample_rate
            wave = math.sin(phase_a) * 0.11 + math.sin(phase_b) * 0.08
            wave += random.uniform(-1.0, 1.0) * 0.22
            swell = 0.55 + 0.45 * math.sin(t * 2.0 * math.pi / seconds) ** 2
            data.append(int(clamp(wave * swell * 0.55, -1.0, 1.0) * 32767))
        return pygame.mixer.Sound(buffer=data.tobytes())

    def _build_sounds(self):
        self.sounds["pitch"]    = self._tone(0.34, 960,  290, volume=0.35, noise=0.45)
        self.sounds["swing"]    = self._tone(0.22, 180,   58, volume=0.36, noise=0.80)
        self.sounds["contact"]  = self._tone(0.20, 126,   62, volume=0.68, noise=0.55, pulse=12.0)
        self.sounds["home_run"] = self._tone(1.15, 392,  784, volume=0.47, noise=0.18, pulse=9.0)
        self.sounds["crowd"]    = self._crowd()
        self.sounds["strike"]   = self._tone(0.18, 220,  110, volume=0.30, noise=0.30)
        self.sounds["walk"]     = self._tone(0.28, 330,  440, volume=0.28, noise=0.10)
        self.sounds["gameOver"] = self._tone(1.60, 392,  196, volume=0.50, noise=0.05, pulse=4.0)


# ─── Pitcher profile ─────────────────────────────────────────────────────────
@dataclass
class PitcherProfile:
    name: str
    arsenal: list[int]       # indices into PITCH_SPECS
    weights: list[float]
    zone_rate: float         # % pitches in zone
    velocity_bonus: int      # added to all speeds


PITCHERS = [
    PitcherProfile("Verlander",  [0, 4, 1], [50, 30, 20], 0.64, +2),
    PitcherProfile("Kershaw",    [2, 0, 3], [45, 35, 20], 0.62, -1),
    PitcherProfile("deGrom",     [0, 6, 1], [48, 28, 24], 0.60, +3),
    PitcherProfile("Scherzer",   [0, 1, 2], [42, 35, 23], 0.58, +1),
    PitcherProfile("Alcantara",  [4, 0, 2], [46, 32, 22], 0.63, 0),
    PitcherProfile("Cole",       [0, 5, 1], [50, 26, 24], 0.61, +2),
    PitcherProfile("Burnes",     [5, 1, 0], [44, 34, 22], 0.59, 0),
    PitcherProfile("Bieber",     [0, 2, 3], [46, 28, 26], 0.65, 0),
    PitcherProfile("Strasburg",  [0, 2, 1], [44, 32, 24], 0.60, 0),
    PitcherProfile("Verlander2", [0, 1, 4], [50, 28, 22], 0.64, +3),  # late-game closer
]


# ─── Pitch ────────────────────────────────────────────────────────────────────
class Pitch:
    def __init__(self, now, pitcher: PitcherProfile):
        self.pitcher = pitcher
        spec_idx = random.choices(pitcher.arsenal, weights=pitcher.weights, k=1)[0]
        self.spec = PITCH_SPECS[spec_idx]
        base_speed = random.randint(self.spec.min_speed, self.spec.max_speed)
        self.speed = clamp(base_speed + pitcher.velocity_bonus, 60, 105)
        self.start_time = now
        real_reaction = 60.5 / (self.speed * MPH_TO_FPS)
        self.duration = clamp(real_reaction * 1.9 + 0.14, 0.72, 1.16)
        self.release_point = pygame.Vector2(WIDTH * 0.5 + random.uniform(-9, 9), 262 + random.uniform(-5, 4))
        self.target_norm = self._choose_target(pitcher.zone_rate)
        self.target_point = norm_to_zone(self.target_norm.x, self.target_norm.y)
        self.tail = []

    @property
    def contact_time(self):
        return self.start_time + self.duration

    @property
    def in_zone(self):
        return abs(self.target_norm.x) <= 1.0 and abs(self.target_norm.y) <= 1.0

    def _choose_target(self, zone_rate):
        in_zone = random.random() < zone_rate
        if in_zone:
            x = random.triangular(-0.95, 0.95, 0.0)
            y = random.triangular(-0.95, 0.95, 0.0)
            if random.random() < 0.28:
                x = random.choice([-1, 1]) * random.uniform(0.74, 1.02)
            if random.random() < 0.26:
                y = random.choice([-1, 1]) * random.uniform(0.72, 1.02)
        else:
            side = random.choice(["left", "right", "high", "low", "corner"])
            if side == "left":
                x = random.uniform(-1.48, -1.08); y = random.uniform(-1.06, 1.08)
            elif side == "right":
                x = random.uniform(1.08, 1.48);  y = random.uniform(-1.06, 1.08)
            elif side == "high":
                x = random.uniform(-1.05, 1.05); y = random.uniform(1.08, 1.42)
            elif side == "low":
                x = random.uniform(-1.05, 1.05); y = random.uniform(-1.42, -1.08)
            else:
                x = random.choice([-1, 1]) * random.uniform(1.02, 1.36)
                y = random.choice([-1, 1]) * random.uniform(1.02, 1.34)
        return pygame.Vector2(x, y)

    def progress(self, now):
        return (now - self.start_time) / self.duration

    def screen_position(self, now):
        t = clamp(self.progress(now), 0.0, 1.12)
        visual_t = smoothstep(clamp(t, 0.0, 1.0))
        base = self.release_point.lerp(self.target_point, visual_t)
        late = math.sin(clamp(t, 0.0, 1.0) * math.pi)
        bend = pygame.Vector2(
            self.spec.horizontal_break * late * (0.45 + 0.55 * t),
            self.spec.vertical_break  * late * (0.35 + 0.65 * t),
        )
        pos = base + bend
        radius = lerp(4.0, 17.0, clamp(t, 0.0, 1.0) ** 1.45)
        return pos, radius


# ─── Fielder ──────────────────────────────────────────────────────────────────
class Fielder:
    def __init__(self, name, x, y, speed, color):
        self.name = name
        self.home = pygame.Vector2(x, y)
        self.pos  = pygame.Vector2(x, y)
        self.speed = float(speed)
        self.color = color

    def reset(self):
        self.pos.update(self.home)

    def move_toward(self, target, dt):
        delta = target - self.pos
        dist = delta.length()
        if dist <= 0.01:
            return
        step = min(dist, self.speed * dt)
        self.pos += delta.normalize() * step


# ─── HitBall ──────────────────────────────────────────────────────────────────
class HitBall:
    def __init__(self, exit_velo, launch_angle, spray_angle, spin_bias=0.0):
        self.pos = pygame.Vector3(0.0, 0.0, 3.1)
        speed = exit_velo * MPH_TO_FPS
        launch  = math.radians(launch_angle)
        spray   = math.radians(spray_angle)
        horizontal = math.cos(launch) * speed
        self.vel = pygame.Vector3(
            math.sin(spray) * horizontal,
            math.cos(spray) * horizontal,
            math.sin(launch) * speed,
        )
        self.spin_bias   = spin_bias
        self.launch_angle = launch_angle
        self.spray_angle  = spray_angle
        self.exit_velo    = exit_velo
        self.elapsed      = 0.0
        self.max_distance = 0.0
        self.max_height   = self.pos.z
        self.first_landing      = None
        self.first_landing_fair = None
        self.bounces   = 0
        self.trail     = []
        self.home_run  = False
        self.foul      = False

    @property
    def on_ground(self):
        return self.pos.z <= 0.05 and abs(self.vel.z) < 2.0

    @property
    def horizontal_speed(self):
        return math.hypot(self.vel.x, self.vel.y)

    def update(self, dt):
        self.elapsed += dt
        drag = math.exp(-0.18 * dt)
        self.vel.x *= drag
        self.vel.y *= drag
        self.vel.x += self.spin_bias * dt
        if not self.on_ground:
            self.vel.z -= GRAVITY * dt
        else:
            friction = max(0.0, 1.0 - 0.92 * dt)
            self.vel.x *= friction
            self.vel.y *= friction
        self.pos.x += self.vel.x * dt
        self.pos.y += self.vel.y * dt
        self.pos.z += self.vel.z * dt
        if self.pos.z <= 0.0:
            if self.first_landing is None and self.pos.y > 8.0:
                self.first_landing = pygame.Vector2(self.pos.x, self.pos.y)
                self.first_landing_fair = fair_at(self.pos.x, self.pos.y)
                self.foul = not self.first_landing_fair
            self.pos.z = 0.0
            if self.vel.z < -7.0 and self.bounces < 4:
                self.vel.z = -self.vel.z * (0.22 if self.launch_angle > 12 else 0.11)
                self.vel.x *= 0.62
                self.vel.y *= 0.62
                self.bounces += 1
            else:
                self.vel.z = 0.0
        dist = distance_ft(self.pos.x, self.pos.y)
        self.max_distance = max(self.max_distance, dist)
        self.max_height   = max(self.max_height, self.pos.z)
        self.trail.append(pygame.Vector3(self.pos.x, self.pos.y, self.pos.z))
        if len(self.trail) > 42:
            self.trail.pop(0)
        if (
            not self.home_run
            and fair_at(self.pos.x, self.pos.y)
            and self.pos.y >= WALL_DISTANCE
            and abs(self.pos.x) < self.pos.y * 0.95
            and self.pos.z > WALL_HEIGHT
        ):
            self.home_run = True


# ─── Pitch history for mini-log ───────────────────────────────────────────────
@dataclass
class PitchResult:
    pitch_name: str
    speed: int
    result: str
    color: tuple[int, int, int]


# ─── Game ─────────────────────────────────────────────────────────────────────
class Game:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Honkbal: PCI Batting v2")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.SCALED)
        self.clock  = pygame.time.Clock()
        self.fonts  = {
            "small":  pygame.font.SysFont("segoeui", 18),
            "body":   pygame.font.SysFont("segoeui", 24),
            "bold":   pygame.font.SysFont("segoeui", 28, bold=True),
            "big":    pygame.font.SysFont("segoeui", 42, bold=True),
            "huge":   pygame.font.SysFont("segoeui", 68, bold=True),
            "score":  pygame.font.SysFont("consolas", 30, bold=True),
            "italic": pygame.font.SysFont("segoeui", 20, italic=True),
        }
        self.sounds   = SoundManager()
        self.particles = ParticleSystem()
        self.running  = True
        self.state    = "result"
        self.state_until = 0.0
        self.game_over = False
        self.game_over_timer = 0.0

        self.pitch: Optional[Pitch] = None
        self.last_pitch = None
        self.hit_ball: Optional[HitBall] = None
        self.fielders = self._make_fielders()
        self.target_fielder  = None
        self.backup_fielder  = None
        self.predicted_landing = pygame.Vector2(0, 230)

        self.pci_pos   = pygame.Vector2(ZONE_CENTER)
        self.swing_mode = "normal"
        self.swing_flash_until = 0.0
        self.swing_flash_kind  = "normal"
        self.has_swung = False
        self.last_swing_time = -10.0

        # Count / score
        self.balls   = 0
        self.strikes = 0
        self.outs    = 0
        self.inning  = 1
        self.top_inning = False   # False = player bats
        self.player_score = 0
        self.cpu_score    = 0
        self.bases = [False, False, False]

        # Stats
        self.stats = BattingStats()

        # Pitcher rotation
        self.pitcher_pool = list(PITCHERS)
        random.shuffle(self.pitcher_pool)
        self.pitcher_index = 0
        self.current_pitcher = self.pitcher_pool[0]

        # Feedback / UI
        self.timing_feedback  = "No Swing"
        self.contact_feedback = ""
        self.pitch_feedback   = "Klik, Space, X of C om te slaan"
        self.result_text      = "Maak de pitcher gek"
        self.secondary_text   = "Beweeg de gele PCI met de muis."
        self.last_hit_distance = 0.0
        self.last_hit_type     = ""
        self.last_exit_velo    = 0.0
        self.cpu_notice        = ""
        self.last_runs_scored  = 0

        # Pitch history log (last 8)
        self.pitch_log: list[PitchResult] = []

        # Streak tracking
        self.hit_streak   = 0
        self.streak_best  = 0

        # Hot-zone toggle
        self.show_hotzone = False

        # Inning score history [[player, cpu], ...]
        self.inning_scores: list[list[int]] = [[0, 0]]

        self.countdown_new_pitch(0.65)

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _make_fielders(self):
        return [
            Fielder("P",  0,    58, 76, (86, 150, 240)),
            Fielder("1B", 88,   94, 78, (86, 150, 240)),
            Fielder("2B", 42,  148, 80, (86, 150, 240)),
            Fielder("SS",-58,  146, 80, (86, 150, 240)),
            Fielder("3B",-88,   94, 78, (86, 150, 240)),
            Fielder("LF",-168, 276, 88, (62, 126, 220)),
            Fielder("CF", 0,   326, 90, (62, 126, 220)),
            Fielder("RF", 168, 276, 88, (62, 126, 220)),
        ]

    def _next_pitcher(self):
        self.pitcher_index = (self.pitcher_index + 1) % len(self.pitcher_pool)
        self.current_pitcher = self.pitcher_pool[self.pitcher_index]

    # ── Main loop ─────────────────────────────────────────────────────────────
    def run(self):
        while self.running:
            dt = min(self.clock.tick(FPS) / 1000.0, 0.033)
            now = pygame.time.get_ticks() / 1000.0
            self.handle_events(now)
            if not self.game_over:
                self.update(dt, now)
            else:
                self.particles.update(dt)
            self.draw(now)
        pygame.quit()

    def handle_events(self, now):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.USEREVENT + 1:
                self.sounds.crowd_normal()
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.running = False
                elif event.key == pygame.K_r:
                    self.reset_game()
                elif event.key == pygame.K_h:
                    self.show_hotzone = not self.show_hotzone
                elif not self.game_over:
                    if event.key == pygame.K_SPACE:
                        self.swing("normal", now)
                    elif event.key == pygame.K_x:
                        self.swing("power", now)
                    elif event.key == pygame.K_c:
                        self.swing("contact", now)
            elif event.type == pygame.MOUSEBUTTONDOWN and not self.game_over:
                if event.button == 1:
                    mods = pygame.key.get_mods()
                    mode = "contact" if mods & pygame.KMOD_SHIFT else "normal"
                    self.swing(mode, now)
                elif event.button == 3:
                    self.swing("power", now)
                elif event.button == 2:
                    self.swing("contact", now)

    def update(self, dt, now):
        mouse = pygame.Vector2(pygame.mouse.get_pos())
        self.pci_pos.x = clamp(mouse.x, PCI_LIMIT.left,  PCI_LIMIT.right)
        self.pci_pos.y = clamp(mouse.y, PCI_LIMIT.top,   PCI_LIMIT.bottom)
        self.particles.update(dt)
        if self.state == "result" and now >= self.state_until:
            self.start_pitch(now)
        elif self.state == "pitch":
            self.update_pitch(now)
        elif self.state == "in_play":
            self.update_in_play(dt, now)

    # ── Game-state helpers ────────────────────────────────────────────────────
    def reset_game(self):
        self.balls = 0; self.strikes = 0; self.outs = 0
        self.inning = 1
        self.player_score = 0; self.cpu_score = 0
        self.bases = [False, False, False]
        self.pitch = None; self.hit_ball = None
        self.stats = BattingStats()
        self.pitch_log.clear()
        self.hit_streak = 0; self.streak_best = 0
        self.inning_scores = [[0, 0]]
        self.game_over = False
        self.pitcher_index = 0
        self.current_pitcher = self.pitcher_pool[0]
        self.result_text   = "Nieuwe wedstrijd"
        self.secondary_text = "Beweeg de gele PCI en time je swing."
        self.particles.particles.clear()
        self.countdown_new_pitch(0.65)

    def countdown_new_pitch(self, delay):
        self.state = "result"
        self.state_until = pygame.time.get_ticks() / 1000.0 + delay

    def start_pitch(self, now):
        if self.game_over:
            return
        self.pitch = Pitch(now, self.current_pitcher)
        self.last_pitch = self.pitch
        self.hit_ball = None
        self.has_swung = False
        self.state = "pitch"
        self.timing_feedback  = "No Swing"
        self.contact_feedback = ""
        self.last_hit_type = ""
        self.pitch_feedback = (
            f"{self.pitch.spec.name}  {self.pitch.speed} mph  |  "
            f"Pitcher: {self.current_pitcher.name}"
        )
        self.result_text   = ""
        self.secondary_text = ""
        self.sounds.play("pitch", 0.48)

    def update_pitch(self, now):
        if not self.pitch:
            return
        pos, radius = self.pitch.screen_position(now)
        last_tail = pygame.Vector2(self.pitch.tail[-1][0], self.pitch.tail[-1][1]) if self.pitch.tail else None
        if last_tail is None or (pos - last_tail).length_squared() > 8:
            self.pitch.tail.append((pos.x, pos.y, radius))
            if len(self.pitch.tail) > 20:
                self.pitch.tail.pop(0)
        if self.pitch.progress(now) >= 1.08 and not self.has_swung:
            if self.pitch.in_zone:
                self.called_strike("Called strike")
            else:
                self.add_ball("Ball")

    # ── Swing ─────────────────────────────────────────────────────────────────
    def swing(self, mode, now):
        if self.state != "pitch" or not self.pitch or self.has_swung:
            return
        self.has_swung = True
        self.last_swing_time = now
        self.swing_flash_until = now + 0.28
        self.swing_flash_kind  = mode
        self.swing_mode = mode
        self.sounds.play("swing", 0.55)

        swing_data = SWING_TYPES[mode]
        timing_offset = now - self.pitch.contact_time
        timing_label, timing_score = self.timing_from_offset(timing_offset, swing_data["timing"])
        self.timing_feedback = timing_label

        target = self.pitch.target_point
        pci_radius = swing_data["pci"]
        dist = (self.pci_pos - target).length()
        contact_radius = pci_radius * swing_data["contact"]
        pci_score = clamp(1.0 - dist / contact_radius, 0.0, 1.0)
        edge_bonus = 0.08 if self.pitch.in_zone else -0.1
        contact_quality = clamp(
            (pci_score * 0.66 + timing_score * 0.42 + edge_bonus) * self.pitch.spec.difficulty,
            0.0, 1.0,
        )

        if timing_score <= 0.0 or contact_quality < 0.27:
            self.contact_feedback = "Miss"
            chase = "Chase strike" if not self.pitch.in_zone else "Swing & miss"
            self.add_strike(chase, swing_miss=True)
            pos, _ = self.pitch.screen_position(now)
            self.particles.emit_strike(pos.x, pos.y)
            return

        self.create_hit(contact_quality, timing_offset, mode)

    def timing_from_offset(self, offset, swing_timing_mod):
        abs_offset = abs(offset)
        perfect = 0.043 * swing_timing_mod
        good    = 0.092 * swing_timing_mod
        ok      = 0.166 * swing_timing_mod
        ugly    = 0.285 * swing_timing_mod
        if abs_offset <= perfect: return "Perfect Timing", 1.00
        if abs_offset <= good:    return "Good Timing",    0.84
        if abs_offset <= ok:      return ("Early" if offset < 0 else "Late"), 0.55
        if abs_offset <= ugly:    return ("Very Early" if offset < 0 else "Very Late"), 0.23
        return ("Very Early" if offset < 0 else "Very Late"), 0.0

    def create_hit(self, quality, timing_offset, mode):
        assert self.pitch is not None
        target = self.pitch.target_point
        diff   = self.pci_pos - target
        swing_data = SWING_TYPES[mode]

        vertical_delta   = diff.y / swing_data["pci"]
        horizontal_delta = diff.x / swing_data["pci"]

        timing_bonus = {
            "Perfect Timing": 8.5, "Good Timing": 4.0,
            "Early": -3.0, "Late": -3.0,
            "Very Early": -11.0, "Very Late": -11.0,
        }.get(self.timing_feedback, 0.0)

        exit_velo = (
            52.0 + quality * 50.0 + timing_bonus
            + (self.pitch.speed - 82) * 0.22
            + random.uniform(-4.5, 4.5)
        ) * swing_data["power"]
        exit_velo = clamp(exit_velo, 42.0, 116.5)

        launch = 9.0 + vertical_delta * 23.0 + quality * 9.0 + random.uniform(-7.0, 7.0)
        if mode == "power":   launch += 3.0
        elif mode == "contact": launch -= 2.5
        if quality < 0.42:    launch += random.uniform(-14.0, 18.0)
        launch = clamp(launch, -10.0, 58.0)

        spray = timing_offset * 154.0 + horizontal_delta * 10.0 + random.uniform(-7.0, 7.0)
        if abs(timing_offset) > 0.13:
            spray += math.copysign(random.uniform(9.0, 18.0), timing_offset)
        if quality < 0.48 and random.random() < 0.45:
            spray += random.choice([-1, 1]) * random.uniform(22.0, 42.0)
        spray = clamp(spray, -68.0, 68.0)

        spin_bias = random.uniform(-3.0, 3.0) + spray * 0.025
        self.hit_ball = HitBall(exit_velo, launch, spray, spin_bias)
        self.last_exit_velo  = exit_velo
        self.last_hit_type   = self.classify_hit_shape(launch)
        self.predicted_landing = self.predict_landing(self.hit_ball)
        self.target_fielder  = self.pick_target_fielder(self.predicted_landing)
        self.backup_fielder  = self.pick_backup_fielder(self.target_fielder, self.predicted_landing)
        for fielder in self.fielders:
            fielder.reset()
        self.state = "in_play"
        self.result_text   = self.last_hit_type
        self.secondary_text = f"Exit velo {exit_velo:.0f} mph | Launch {launch:.0f}°"
        self.sounds.play("contact", 0.8)
        # Particles at PCI center
        self.particles.emit_hit(self.pci_pos.x, self.pci_pos.y, quality)

        # Stats — update exit velo
        self.stats.total_exit_velo += exit_velo
        self.stats.hit_count_for_ev += 1
        self.stats.max_exit_velo = max(self.stats.max_exit_velo, exit_velo)

    def classify_hit_shape(self, launch):
        if launch <  7: return "Ground Ball"
        if launch < 18: return "Line Drive"
        if launch < 37: return "Fly Ball"
        return "High Fly"

    def predict_landing(self, ball):
        sim = HitBall(ball.exit_velo, ball.launch_angle, ball.spray_angle, ball.spin_bias)
        last = pygame.Vector2(0, 120)
        for _ in range(480):
            sim.update(1.0 / 90.0)
            last = pygame.Vector2(sim.pos.x, sim.pos.y)
            if sim.first_landing is not None:
                return sim.first_landing
            if sim.home_run:
                return pygame.Vector2(sim.pos.x, WALL_DISTANCE)
        return last

    def pick_target_fielder(self, landing):
        best, best_dist = None, 9999
        for f in self.fielders:
            d = (f.pos - landing).length()
            if d < best_dist:
                best, best_dist = f, d
        return best

    def pick_backup_fielder(self, primary, landing):
        best, best_dist = None, 9999
        for f in self.fielders:
            if f is primary: continue
            d = (f.pos - landing).length()
            if d < best_dist:
                best, best_dist = f, d
        return best

    def update_fielder_routes(self, ball, dt):
        primary = self.target_fielder or self.pick_target_fielder(pygame.Vector2(ball.pos.x, ball.pos.y))
        self.target_fielder = primary
        if self.backup_fielder is None:
            self.backup_fielder = self.pick_backup_fielder(primary, self.predicted_landing)
        live_ball   = pygame.Vector2(ball.pos.x, ball.pos.y)
        play_target = live_ball if ball.on_ground or ball.first_landing is not None else self.predicted_landing
        cutoff_target = pygame.Vector2(play_target.x * 0.62, max(88.0, play_target.y * 0.58))
        base_cover = {
            "P":  pygame.Vector2(52, 82),   "1B": pygame.Vector2(90, 90),
            "2B": pygame.Vector2(0, 180),   "SS": pygame.Vector2(-90, 90),
            "3B": pygame.Vector2(-90, 90),  "LF": pygame.Vector2(-118, 205),
            "CF": pygame.Vector2(0, 235),   "RF": pygame.Vector2(118, 205),
        }
        for fielder in self.fielders:
            if fielder is primary:
                route = play_target
                speed_mod = 1.0 if ball.first_landing is None else 1.14
            elif fielder is self.backup_fielder:
                route = cutoff_target; speed_mod = 0.76
            else:
                route = base_cover.get(fielder.name, fielder.home); speed_mod = 0.54
            old = fielder.speed
            fielder.speed = old * speed_mod
            fielder.move_toward(route, dt)
            fielder.speed = old

    def update_in_play(self, dt, now):
        if not self.hit_ball:
            return
        ball = self.hit_ball
        ball.update(dt)
        if ball.home_run:
            self.resolve_batted_ball("Home Run", out=False, bases=4, special="No doubt!")
            self.sounds.play("home_run", 0.95)
            self.sounds.crowd_surge(0.7)
            cx, cy = world_to_screen(ball.pos.x, ball.pos.y, ball.pos.z)
            self.particles.emit_homerun(cx, cy)
            return
        fair_now = fair_at(ball.pos.x, ball.pos.y) if ball.first_landing_fair is None else ball.first_landing_fair
        self.update_fielder_routes(ball, dt)
        primary = self.target_fielder or min(self.fielders, key=lambda f: (f.pos - pygame.Vector2(ball.pos.x, ball.pos.y)).length_squared())
        fielder_dist = (primary.pos - pygame.Vector2(ball.pos.x, ball.pos.y)).length()
        catch_radius = 9.5
        if ball.launch_angle < 12: catch_radius = 6.0
        elif ball.max_height > 75: catch_radius = 11.5
        if not ball.on_ground and ball.vel.z < 0 and ball.pos.z <= 10.0 and fielder_dist <= catch_radius:
            if fair_now:
                self.resolve_batted_ball("Caught", out=True, bases=0, special=f"{primary.name} makes the catch")
            else:
                self.resolve_batted_ball("Foul Out", out=True, bases=0, special=f"{primary.name} catches it foul")
            return
        if ball.first_landing is not None and not ball.first_landing_fair:
            if ball.elapsed > 0.6 and (ball.on_ground or ball.pos.z < 2.0):
                self.resolve_foul(ball.max_distance)
            return
        if ball.on_ground and fielder_dist <= 8.0 and ball.elapsed > 0.35:
            self.resolve_ground_fielded(primary)
            return
        if ball.elapsed > 8.5 or (ball.on_ground and ball.horizontal_speed < 4.0 and ball.elapsed > 1.3):
            self.resolve_open_ball()

    # ── Resolve helpers ───────────────────────────────────────────────────────
    def _log_pitch(self, result: str):
        if not self.pitch and not self.last_pitch:
            return
        p = self.last_pitch
        if p:
            color_map = {
                "Single": (120, 240, 140), "Double": (255, 230, 90),
                "Triple": (255, 170, 60),  "Home Run": (255, 100, 100),
                "Strike": (255, 90, 90),   "Ball": (120, 200, 255),
                "Walk":   (120, 200, 255), "Out": (200, 200, 210),
                "Foul":   (200, 180, 120),
            }
            key = next((k for k in color_map if k in result), "Out")
            self.pitch_log.append(PitchResult(p.spec.name, p.speed, result, color_map[key]))
            if len(self.pitch_log) > 8:
                self.pitch_log.pop(0)

    def resolve_ground_fielded(self, fielder):
        assert self.hit_ball is not None
        ball = self.hit_ball
        first_base = pygame.Vector2(90, 90)
        throw_time  = (fielder.pos - first_base).length() / 122.0 + 0.33
        runner_time = 4.18
        infield_grounder = ball.max_distance < 145 and ball.launch_angle < 8
        hard_to_side     = abs(ball.spray_angle) > 28 and ball.exit_velo > 88
        if infield_grounder and not hard_to_side and ball.elapsed + throw_time < runner_time + random.uniform(-0.12, 0.22):
            self.resolve_batted_ball("Ground Out", out=True, bases=0, special=f"{fielder.name} throws to first")
            return
        bases = max(1, self.bases_from_distance(ball.max_distance, ball.launch_angle, ball.spray_angle))
        label = ["", "Single", "Double", "Triple"][bases]
        self.resolve_batted_ball(label, out=False, bases=bases, special=f"{fielder.name} fields it")

    def resolve_open_ball(self):
        assert self.hit_ball is not None
        ball = self.hit_ball
        bases = self.bases_from_distance(ball.max_distance, ball.launch_angle, ball.spray_angle)
        label = ["", "Single", "Double", "Triple"][bases]
        if bases == 0:
            self.resolve_batted_ball("Out", out=True, bases=0, special="Routine play")
        else:
            self.resolve_batted_ball(label, out=False, bases=bases, special="Ball drops in")

    def bases_from_distance(self, dist, launch, spray):
        if dist > 342 and abs(spray) > 22: return 3
        if dist > 262 or (dist > 205 and launch > 15): return 2
        if dist > 72: return 1
        return 0

    def resolve_foul(self, dist):
        self.last_hit_distance = dist
        self._log_pitch("Foul")
        if self.strikes < 2:
            self.strikes += 1
            self.result_text = "Foul Ball"
            self.secondary_text = f"Strike {self.strikes} | {dist:.0f} ft"
        else:
            self.result_text   = "Foul Ball"
            self.secondary_text = f"Blijft {self.balls}-{self.strikes} | {dist:.0f} ft"
        self.hit_ball = None
        self.pitch    = None
        self.state    = "result"
        self.state_until = pygame.time.get_ticks() / 1000.0 + 1.35

    def resolve_batted_ball(self, label, out, bases, special=""):
        assert self.hit_ball is not None
        self.last_hit_distance = self.hit_ball.max_distance
        runs_scored = 0
        self.stats.plate_appearances += 1

        if out:
            self.outs += 1
            self.stats.at_bats += 1
            self.hit_streak = 0
            if "Strike" in label or label == "Swing & miss":
                self.stats.strikeouts += 1
            self._log_pitch("Out")
        elif bases > 0:
            self.stats.at_bats += 1
            self.stats.hits += 1
            self.hit_streak += 1
            self.streak_best = max(self.streak_best, self.hit_streak)
            runs_scored = self.advance_runners(bases, self.hit_ball)
            if bases == 1:   self.stats.singles += 1;    self._log_pitch("Single")
            elif bases == 2: self.stats.doubles += 1;    self._log_pitch("Double")
            elif bases == 3: self.stats.triples += 1;    self._log_pitch("Triple")
            elif bases == 4:
                self.stats.home_runs += 1
                self._log_pitch("Home Run")
            self.stats.rbi += runs_scored
            self.stats.max_distance = max(self.stats.max_distance, self.last_hit_distance)
            if runs_scored >= 1:
                self.sounds.crowd_surge(0.55)

        self.last_runs_scored = runs_scored
        self.result_text = label
        dist_m = self.last_hit_distance * 0.3048
        run_text = ""
        if runs_scored == 1:   run_text = " | 1 run scoort"
        elif runs_scored > 1:  run_text = f" | {runs_scored} runs scoren"
        self.secondary_text = f"{special}{run_text} | {self.last_hit_distance:.0f} ft / {dist_m:.0f} m"
        self.balls = 0; self.strikes = 0
        self.hit_ball = None; self.pitch = None
        delay = 2.2 if label == "Home Run" else 1.55
        self.check_inning_end()
        self.state = "result"
        self.state_until = pygame.time.get_ticks() / 1000.0 + delay

    def add_ball(self, text):
        self._log_pitch("Ball")
        self.balls += 1
        self.result_text   = text
        self.secondary_text = f"Stand {self.balls}-{self.strikes}"
        self.pitch = None
        if self.balls >= 4:
            self.walk(); return
        self.state = "result"
        self.state_until = pygame.time.get_ticks() / 1000.0 + 0.95

    def called_strike(self, text):
        self.add_strike(text, swing_miss=False)

    def add_strike(self, text, swing_miss=False):
        self._log_pitch("Strike")
        self.strikes += 1
        self.result_text   = text
        self.secondary_text = f"Stand {self.balls}-{self.strikes}"
        self.pitch = None
        self.sounds.play("strike", 0.4)
        if self.strikes >= 3:
            self.outs += 1
            self.stats.plate_appearances += 1
            self.stats.at_bats += 1
            self.stats.strikeouts += 1
            self.hit_streak = 0
            self.result_text   = "Strikeout"
            self.secondary_text = "Drie strikes"
            self.balls = 0; self.strikes = 0
            self.check_inning_end()
            self.state = "result"
            self.state_until = pygame.time.get_ticks() / 1000.0 + 1.45
            return
        self.state = "result"
        self.state_until = pygame.time.get_ticks() / 1000.0 + (1.05 if swing_miss else 0.95)

    def walk(self):
        self._log_pitch("Walk")
        self.stats.plate_appearances += 1
        self.stats.walks += 1
        self.result_text   = "Walk"
        self.secondary_text = "Vier ballen"
        self.force_walk_runners()
        self.balls = 0; self.strikes = 0
        self.pitch = None
        self.sounds.play("walk", 0.5)
        self.state = "result"
        self.state_until = pygame.time.get_ticks() / 1000.0 + 1.3

    def force_walk_runners(self):
        if self.bases[0] and self.bases[1] and self.bases[2]:
            self.player_score += 1
            if self.inning_scores:
                self.inning_scores[-1][0] += 1
        if self.bases[0] and self.bases[1]: self.bases[2] = True
        if self.bases[0]:                   self.bases[1] = True
        self.bases[0] = True

    def advance_runners(self, bases, ball=None):
        if bases >= 4:
            runs = 1 + sum(1 for o in self.bases if o)
            self.bases = [False, False, False]
            self.player_score += runs
            if self.inning_scores:
                self.inning_scores[-1][0] += runs
            return runs
        dist  = ball.max_distance if ball else 140
        spray = abs(ball.spray_angle) if ball else 0
        deep_gap = dist > 205 or spray > 30
        runs = 0
        new_bases = [False, False, False]
        for idx in range(2, -1, -1):
            if not self.bases[idx]: continue
            advance = bases
            if bases == 1:
                if idx == 1 and (dist > 135 or deep_gap or random.random() < 0.58): advance = 2
                elif idx == 0 and (dist > 205 or random.random() < 0.2):            advance = 2
            elif bases == 2 and idx == 0 and (dist > 285 or deep_gap or random.random() < 0.46):
                advance = 3
            new_index = idx + advance
            if new_index >= 3: runs += 1
            else: new_bases[new_index] = True
        if bases < 4:
            new_bases[bases - 1] = True
        self.bases = new_bases
        self.player_score += runs
        if self.inning_scores:
            self.inning_scores[-1][0] += runs
        return runs

    def check_inning_end(self):
        if self.outs < 3:
            return
        cpu_runs = random.choices([0, 1, 2, 3], weights=[50, 30, 15, 5], k=1)[0]
        self.cpu_score += cpu_runs
        if self.inning_scores:
            self.inning_scores[-1][1] = cpu_runs
        self.cpu_notice = f"CPU scoort {cpu_runs} in de andere helft"
        self.outs = 0
        self.bases = [False, False, False]
        self.balls = 0; self.strikes = 0
        self.inning += 1
        self.secondary_text = f"{self.secondary_text} | {self.cpu_notice}"
        # Rotate pitcher every 3 innings
        if self.inning % 3 == 1:
            self._next_pitcher()
        if self.inning > MAX_INNINGS:
            self._trigger_game_over()
            return
        self.inning_scores.append([0, 0])

    def _trigger_game_over(self):
        self.game_over = True
        self.sounds.play("gameOver", 0.7)
        # Big fireworks if player wins
        if self.player_score > self.cpu_score:
            for _ in range(4):
                self.particles.emit_homerun(
                    random.randint(200, 1080),
                    random.randint(150, 400),
                )

    # ══════════════════════════════════════════════════════════════════════════
    # DRAWING
    # ══════════════════════════════════════════════════════════════════════════
    def draw(self, now):
        if self.state == "in_play":
            self.draw_field_view(now)
        else:
            self.draw_batter_view(now)
        self.particles.draw(self.screen)
        self.draw_hud(now)
        if self.game_over:
            self.draw_game_over(now)
        pygame.display.flip()

    # ── Batter view ───────────────────────────────────────────────────────────
    def draw_batter_view(self, now):
        self.draw_sky_and_stands()
        self.draw_infield_perspective()
        self.draw_pitcher(now)
        self.draw_strike_zone()
        if self.show_hotzone:
            self.draw_hot_zones()
        if self.pitch:
            self.draw_pitch(now)
        self.draw_pci(now)
        if now < self.swing_flash_until:
            self.draw_bat_swing(now)
        self.draw_center_feedback(now)

    def draw_sky_and_stands(self):
        for y in range(0, HEIGHT):
            ratio = y / HEIGHT
            if y < 340:
                c = (int(18+20*ratio), int(33+42*ratio), int(58+58*ratio))
            else:
                c = (int(26+12*ratio), int(76+48*ratio), int(43+18*ratio))
            pygame.draw.line(self.screen, c, (0, y), (WIDTH, y))
        pygame.draw.rect(self.screen, (15, 22, 33), (0, 95, WIDTH, 124))
        pygame.draw.rect(self.screen, (23, 30, 42), (0, 142, WIDTH, 96))
        for row in range(4):
            y = 112 + row * 24
            for x in range(8, WIDTH, 18):
                shade = 54 + ((x + row*19) % 60)
                pygame.draw.circle(self.screen, (shade, shade+6, shade+18), (x, y), 3)
        pygame.draw.rect(self.screen, (37, 84, 61), (0, 224, WIDTH, 70))
        pygame.draw.rect(self.screen, (74, 58, 46), (0, 292, WIDTH, 22))
        for x in range(72, WIDTH, 180):
            pygame.draw.circle(self.screen, (255, 247, 191), (x, 72), 5)
            pygame.draw.line(self.screen, (91, 103, 116), (x, 72), (x+12, 205), 2)

    def draw_infield_perspective(self):
        mound = pygame.Rect(574, 302, 132, 28)
        pygame.draw.ellipse(self.screen, (148, 105, 70), mound)
        pygame.draw.ellipse(self.screen, (102,  72, 48), mound, 3)
        plate = [(604, 636), (676, 636), (690, 660), (640, 684), (590, 660)]
        pygame.draw.polygon(self.screen, (226, 225, 208), plate)
        pygame.draw.polygon(self.screen, (42, 45, 42), plate, 2)
        pygame.draw.line(self.screen, (183, 142, 99), (640, 662), (1020, 357), 4)
        pygame.draw.line(self.screen, (183, 142, 99), (640, 662), (260, 357), 4)
        pygame.draw.arc(self.screen, (130, 92, 62), (418, 438, 444, 180), math.pi, math.tau, 3)

    def draw_pitcher(self, now):
        base = pygame.Vector2(WIDTH * 0.5, 276)
        progress = clamp(self.pitch.progress(now), 0.0, 1.0) if self.pitch else 0.0
        leg = math.sin(progress * math.pi * 2.0) * 12
        arm = math.sin(progress * math.pi * 2.4) * 24
        shadow = pygame.Rect(base.x - 36, base.y + 42, 72, 13)
        pygame.draw.ellipse(self.screen, (40, 50, 45), shadow)
        pygame.draw.circle(self.screen, (230, 196, 158), (int(base.x), int(base.y - 52)), 15)
        pygame.draw.rect(self.screen, (235, 238, 245), (base.x-15, base.y-38, 30, 45), border_radius=7)
        pygame.draw.rect(self.screen, (58,  90, 162), (base.x-16, base.y-5,  32, 25), border_radius=5)
        pygame.draw.line(self.screen, (235, 238, 245), (base.x-13, base.y-28), (base.x-42, base.y-10-arm), 7)
        pygame.draw.line(self.screen, (235, 238, 245), (base.x+13, base.y-28), (base.x+38, base.y-26+arm*0.35), 7)
        pygame.draw.line(self.screen, (45, 63, 102), (base.x-9, base.y+18), (base.x-25, base.y+54+leg), 8)
        pygame.draw.line(self.screen, (45, 63, 102), (base.x+9, base.y+18), (base.x+24, base.y+54-leg*0.2), 8)
        pygame.draw.circle(self.screen, (35, 42, 54), (int(base.x), int(base.y-70)), 12)
        # Pitcher name tag
        name_surf = self.fonts["small"].render(self.current_pitcher.name, True, (210, 220, 240))
        self.screen.blit(name_surf, name_surf.get_rect(center=(int(base.x), int(base.y + 72))))

    def draw_strike_zone(self):
        overlay = pygame.Surface((STRIKE_ZONE.width, STRIKE_ZONE.height), pygame.SRCALPHA)
        overlay.fill((30, 38, 48, 52))
        pygame.draw.rect(overlay, (220, 230, 244, 126), overlay.get_rect(), 2, border_radius=3)
        for i in (1, 2):
            x = i * STRIKE_ZONE.width / 3
            y = i * STRIKE_ZONE.height / 3
            pygame.draw.line(overlay, (220, 230, 244, 72), (x, 0), (x, STRIKE_ZONE.height), 1)
            pygame.draw.line(overlay, (220, 230, 244, 72), (0, y), (STRIKE_ZONE.width, y), 1)
        self.screen.blit(overlay, STRIKE_ZONE.topleft)

    def draw_hot_zones(self):
        """Draw hot/cold zone overlay on strike zone based on PCI distance heuristic."""
        cell_w = STRIKE_ZONE.width  // 3
        cell_h = STRIKE_ZONE.height // 3
        pci_r  = SWING_TYPES[self.swing_mode]["pci"]
        for row in range(3):
            for col in range(3):
                cx = STRIKE_ZONE.left + col * cell_w + cell_w // 2
                cy = STRIKE_ZONE.top  + row * cell_h + cell_h // 2
                # distance from PCI center to cell center
                dist = math.hypot(cx - self.pci_pos.x, cy - self.pci_pos.y)
                coverage = clamp(1.0 - dist / pci_r, 0.0, 1.0)
                r = int(lerp(180, 80,  coverage))
                g = int(lerp( 60, 200, coverage))
                b = int(lerp( 60, 80,  coverage))
                cell_surf = pygame.Surface((cell_w, cell_h), pygame.SRCALPHA)
                cell_surf.fill((r, g, b, int(coverage * 110 + 20)))
                self.screen.blit(cell_surf, (STRIKE_ZONE.left + col*cell_w, STRIKE_ZONE.top + row*cell_h))

    def draw_pitch(self, now):
        assert self.pitch is not None
        for i, item in enumerate(self.pitch.tail):
            x, y, r = item
            alpha = i / max(1, len(self.pitch.tail) - 1)
            color = tuple(int(c * alpha) for c in self.pitch.spec.color)
            pygame.draw.circle(self.screen, color, (int(x), int(y)), max(1, int(r * 0.42)))
        pos, radius = self.pitch.screen_position(now)
        pygame.draw.circle(self.screen, (250, 250, 246), (int(pos.x), int(pos.y)), int(radius))
        pygame.draw.circle(self.screen, (156, 38, 44), (int(pos.x - radius*0.15), int(pos.y)), max(1, int(radius*0.16)))
        pygame.draw.arc(
            self.screen, (170, 42, 48),
            (pos.x - radius*0.72, pos.y - radius*0.68, radius*1.4, radius*1.36),
            -1.0, 1.0, max(1, int(radius*0.13)),
        )
        # Speed label near ball
        if radius > 9:
            spd = self.fonts["small"].render(f"{self.pitch.speed}", True, (255, 240, 200))
            self.screen.blit(spd, (int(pos.x) + int(radius) + 4, int(pos.y) - 8))

    def draw_pci(self, now):
        data   = SWING_TYPES[self.swing_mode]
        radius = data["pci"] * (0.92 + 0.04 * math.sin(now * 8.0))
        center = (int(self.pci_pos.x), int(self.pci_pos.y))
        pygame.draw.circle(self.screen, (255, 218, 44), center, int(radius), 3)
        pygame.draw.circle(self.screen, (255, 242, 126), center, 7)
        pygame.draw.circle(self.screen, (40, 35, 8),    center, 3)
        for angle in (0, math.pi/2, math.pi, math.pi*1.5):
            inner = pygame.Vector2(math.cos(angle), math.sin(angle)) * (radius * 0.35)
            outer = pygame.Vector2(math.cos(angle), math.sin(angle)) * (radius * 0.64)
            pygame.draw.line(self.screen, (255, 230, 64), self.pci_pos + inner, self.pci_pos + outer, 4)

    def draw_bat_swing(self, now):
        age  = 1.0 - clamp((self.swing_flash_until - now) / 0.28, 0.0, 1.0)
        side = -1 if self.swing_flash_kind != "power" else 1
        arc_rect = pygame.Rect(486, 544, 310, 180)
        start = math.radians(205 - age*105) if side < 0 else math.radians(-25 + age*105)
        end   = start + math.radians(55)
        color = (224, 178, 101) if self.swing_flash_kind != "power" else (247, 205, 111)
        pygame.draw.arc(self.screen, color, arc_rect, start, end, 8)

    def draw_center_feedback(self, now):
        if not self.result_text and self.state == "pitch":
            return
        title = self.result_text
        sub   = self.secondary_text
        if title:
            surf   = self.fonts["big"].render(title, True, (246, 248, 252))
            shadow = self.fonts["big"].render(title, True, (18, 22, 30))
            rect   = surf.get_rect(center=(WIDTH // 2, 116))
            self.screen.blit(shadow, rect.move(2, 2))
            self.screen.blit(surf,   rect)
        if sub:
            surf = self.fonts["body"].render(sub, True, (222, 227, 235))
            rect = surf.get_rect(center=(WIDTH // 2, 158))
            self.screen.blit(surf, rect)

    # ── Field view ────────────────────────────────────────────────────────────
    def draw_field_view(self, now):
        self.draw_field_background()
        self.draw_field_lines()
        for fielder in self.fielders:
            self.draw_fielder(fielder)
        if self.hit_ball:
            self.draw_hit_ball()
        self.draw_center_feedback(now)

    def draw_field_background(self):
        self.screen.fill((28, 91, 55))
        pygame.draw.rect(self.screen, (18, 31, 45), (0, 0, WIDTH, 118))
        for x in range(0, WIDTH, 24):
            pygame.draw.circle(self.screen, (50+x%37, 56, 75), (x+8, 74+(x%5)), 3)
        pygame.draw.arc(self.screen, (35, 115, 68), (-44, 86, WIDTH+88, 970), math.radians(202), math.radians(338), 80)
        pygame.draw.arc(self.screen, (31,  74, 52), (-34, 116, WIDTH+68, 910), math.radians(202), math.radians(338), 16)
        pygame.draw.polygon(self.screen, (145, 99, 61), [
            world_to_screen(0, 0), world_to_screen(90, 90),
            world_to_screen(0, 180), world_to_screen(-90, 90),
        ])
        pygame.draw.circle(self.screen, (136, 91, 58), world_to_screen(0, 60), 24)

    def draw_field_lines(self):
        white = (226, 226, 210)
        pygame.draw.line(self.screen, white, world_to_screen(0,0), world_to_screen(-430, 430), 3)
        pygame.draw.line(self.screen, white, world_to_screen(0,0), world_to_screen( 430, 430), 3)
        # Wall arc
        pts = []
        for angle_deg in range(-50, 51, 3):
            a = math.radians(angle_deg)
            x = WALL_DISTANCE * math.sin(a)
            y = WALL_DISTANCE * math.cos(a)
            sp = world_to_screen(x, y)
            pts.append(sp)
        if len(pts) > 1:
            pygame.draw.lines(self.screen, (64, 148, 88), False, pts, 4)
        bases_coords = [pygame.Vector2(90, 90), pygame.Vector2(0, 180), pygame.Vector2(-90, 90)]
        for i, base in enumerate(bases_coords):
            color = (255, 225, 105) if self.bases[i] else (245, 244, 230)
            points = [
                world_to_screen(base.x, base.y+5), world_to_screen(base.x+5, base.y),
                world_to_screen(base.x, base.y-5), world_to_screen(base.x-5, base.y),
            ]
            pygame.draw.polygon(self.screen, color, points)
        pygame.draw.polygon(self.screen, (245, 244, 230), [
            world_to_screen(0,-4), world_to_screen(7,2),
            world_to_screen(0, 8), world_to_screen(-7, 2),
        ])

    def draw_fielder(self, fielder):
        p = world_to_screen(fielder.pos.x, fielder.pos.y)
        pygame.draw.ellipse(self.screen, (18, 45, 31), (p.x-10, p.y+8, 20, 7))
        pygame.draw.circle(self.screen, fielder.color, (int(p.x), int(p.y)), 9)
        pygame.draw.circle(self.screen, (237, 220, 190), (int(p.x), int(p.y-9)), 5)
        label = self.fonts["small"].render(fielder.name, True, (236, 240, 248))
        self.screen.blit(label, label.get_rect(center=(p.x, p.y+21)))

    def draw_hit_ball(self):
        ball = self.hit_ball
        assert ball is not None
        for i, pt in enumerate(ball.trail):
            alpha = (i + 1) / len(ball.trail)
            p = world_to_screen(pt.x, pt.y, pt.z)
            pygame.draw.circle(self.screen, (int(255*alpha), int(230*alpha), int(145*alpha)), p, max(1, int(2+alpha*3)))
        shadow = world_to_screen(ball.pos.x, ball.pos.y, 0)
        pygame.draw.ellipse(self.screen, (18, 49, 31), (shadow.x-6, shadow.y-2, 12, 5))
        p = world_to_screen(ball.pos.x, ball.pos.y, ball.pos.z)
        pygame.draw.circle(self.screen, (255, 252, 238), (int(p.x), int(p.y)), 6)
        pygame.draw.circle(self.screen, (178,  39,  44), (int(p.x-2), int(p.y)), 2)
        self.last_hit_distance = ball.max_distance
        # Height indicator
        if ball.pos.z > 2:
            ht = self.fonts["small"].render(f"{ball.pos.z:.0f} ft", True, (255, 255, 220))
            self.screen.blit(ht, (int(p.x)+8, int(p.y)-14))

    # ── HUD ───────────────────────────────────────────────────────────────────
    def draw_hud(self, now):
        self.draw_score_bug()
        self.draw_feedback_panel()
        self.draw_timing_bar()
        self.draw_controls_strip()
        self.draw_pitch_log()
        self.draw_stats_panel()
        if self.state == "in_play":
            self.draw_in_play_panel()

    def draw_score_bug(self):
        panel = pygame.Surface((300, 188), pygame.SRCALPHA)
        panel.fill((12, 16, 24, 210))
        pygame.draw.rect(panel, (255, 255, 255, 38), panel.get_rect(), 1, border_radius=6)
        self.screen.blit(panel, (20, 18))
        title = self.fonts["score"].render(f"JIJ {self.player_score}  CPU {self.cpu_score}", True, (248, 250, 255))
        self.screen.blit(title, (38, 30))
        inn_str = f"Inning {self.inning}/{MAX_INNINGS}"
        inning  = self.fonts["body"].render(inn_str, True, (205, 214, 226))
        self.screen.blit(inning, (39, 66))
        self.draw_count_dots("Balls",   self.balls,   4, (79, 224, 132), 40, 110)
        self.draw_count_dots("Strikes", self.strikes, 3, (245, 188, 70), 40, 136)
        self.draw_count_dots("Outs",    self.outs,    3, (255, 97, 97),  40, 162)
        self.draw_bases(242, 136)

    def draw_count_dots(self, label, count, total, color, x, y):
        text = self.fonts["small"].render(label, True, (205, 214, 226))
        self.screen.blit(text, (x, y - 10))
        for i in range(total):
            fill = color if i < count else (65, 72, 84)
            pygame.draw.circle(self.screen, fill, (x + 88 + i * 20, y), 7)

    def draw_bases(self, cx, cy):
        points = [(cx, cy-27), (cx+26, cy), (cx, cy+27), (cx-26, cy)]
        pygame.draw.polygon(self.screen, (57, 64, 74), points, 2)
        base_positions = [(cx+25, cy), (cx, cy-25), (cx-25, cy)]
        for occupied, pos in zip(self.bases, base_positions):
            color = (255, 225, 105) if occupied else (42, 48, 58)
            diamond = [(pos[0], pos[1]-8), (pos[0]+8, pos[1]), (pos[0], pos[1]+8), (pos[0]-8, pos[1])]
            pygame.draw.polygon(self.screen, color, diamond)
            pygame.draw.polygon(self.screen, (229, 235, 245), diamond, 1)

    def draw_feedback_panel(self):
        panel = pygame.Surface((346, 168), pygame.SRCALPHA)
        panel.fill((12, 16, 24, 190))
        pygame.draw.rect(panel, (255, 255, 255, 34), panel.get_rect(), 1, border_radius=6)
        x = WIDTH - 366
        y = 18
        self.screen.blit(panel, (x, y))
        timing_color = TIMING_COLORS.get(self.timing_feedback, (232, 236, 244))
        lines = [
            ("Pitch",   self.pitch_feedback,                                    (232, 236, 244)),
            ("Timing",  self.timing_feedback,                                   timing_color),
            ("Contact", self.contact_feedback or self.last_hit_type or "-",     (255, 232, 132)),
            ("Swing",   SWING_TYPES[self.swing_mode]["label"],                  (215, 224, 238)),
        ]
        for idx, (label, value, color) in enumerate(lines):
            yy = y + 20 + idx * 34
            left  = self.fonts["small"].render(label.upper(), True, (142, 153, 170))
            right = self.fonts["body"].render(value, True, color)
            self.screen.blit(left,  (x + 18, yy + 5))
            self.screen.blit(right, (x + 106, yy))

    def draw_timing_bar(self):
        """Horizontal timing quality bar shown below feedback panel."""
        quality = TIMING_QUALITY.get(self.timing_feedback, 0.0)
        color   = TIMING_COLORS.get(self.timing_feedback, (200, 200, 200))
        x = WIDTH - 366
        y = 200
        bar_w, bar_h = 346, 14
        bg = pygame.Surface((bar_w, bar_h), pygame.SRCALPHA)
        bg.fill((30, 36, 48, 160))
        self.screen.blit(bg, (x, y))
        fill_w = int(bar_w * quality)
        if fill_w > 2:
            pygame.draw.rect(self.screen, color, (x, y, fill_w, bar_h), border_radius=4)
        pygame.draw.rect(self.screen, (100, 110, 130, 180), (x, y, bar_w, bar_h), 1, border_radius=4)
        label = self.fonts["small"].render("TIMING", True, (160, 170, 185))
        self.screen.blit(label, (x + 4, y + 1))

    def draw_pitch_log(self):
        """Last 8 pitches shown as small color-coded pills."""
        if not self.pitch_log:
            return
        x0 = WIDTH - 366
        y0 = 226
        panel = pygame.Surface((346, 14 + len(self.pitch_log)*22), pygame.SRCALPHA)
        panel.fill((12, 16, 24, 160))
        self.screen.blit(panel, (x0, y0))
        header = self.fonts["small"].render("LAATSTE WORPEN", True, (140, 150, 170))
        self.screen.blit(header, (x0 + 8, y0 + 2))
        for i, pr in enumerate(reversed(self.pitch_log)):
            yy = y0 + 18 + i * 22
            dot = pygame.Surface((8, 8), pygame.SRCALPHA)
            pygame.draw.circle(dot, pr.color, (4, 4), 4)
            self.screen.blit(dot, (x0 + 8, yy + 4))
            line = f"{pr.pitch_name} {pr.speed}mph  {pr.result}"
            surf = self.fonts["small"].render(line, True, pr.color)
            self.screen.blit(surf, (x0 + 20, yy))

    def draw_stats_panel(self):
        """Compact stats in bottom-right corner."""
        stats = self.stats
        avg_str = f"{stats.avg:.3f}".lstrip("0") or ".000"
        slg_str = f"{stats.slugging:.3f}".lstrip("0") or ".000"
        obp_str = f"{stats.obp:.3f}".lstrip("0") or ".000"
        lines = [
            f"AVG {avg_str}  SLG {slg_str}  OBP {obp_str}",
            f"HR {stats.home_runs}  2B {stats.doubles}  3B {stats.triples}  1B {stats.singles}  BB {stats.walks}  K {stats.strikeouts}",
            f"Reeks {self.hit_streak} |  Best {self.streak_best}  |  EV {stats.avg_exit_velo:.0f} mph",
        ]
        x0 = 20
        y0 = HEIGHT - 118
        panel_h = 14 + len(lines) * 22
        panel = pygame.Surface((540, panel_h), pygame.SRCALPHA)
        panel.fill((12, 16, 24, 170))
        pygame.draw.rect(panel, (255, 255, 255, 28), panel.get_rect(), 1, border_radius=5)
        self.screen.blit(panel, (x0, y0))
        for i, line in enumerate(lines):
            surf = self.fonts["small"].render(line, True, (200, 215, 235))
            self.screen.blit(surf, (x0 + 10, y0 + 6 + i * 22))

    def draw_controls_strip(self):
        text = "Muis: PCI  |  Klik/Space: normaal  |  Rechtermuisknop/X: power  |  Shift+klik/C: contact  |  H: hot-zones  |  R: reset"
        surf = self.fonts["small"].render(text, True, (216, 224, 236))
        bg   = pygame.Surface((surf.get_width() + 28, 34), pygame.SRCALPHA)
        bg.fill((11, 15, 22, 172))
        rect = bg.get_rect(center=(WIDTH // 2, HEIGHT - 24))
        self.screen.blit(bg,   rect)
        self.screen.blit(surf, surf.get_rect(center=rect.center))

    def draw_in_play_panel(self):
        panel = pygame.Surface((284, 86), pygame.SRCALPHA)
        panel.fill((12, 16, 24, 194))
        pygame.draw.rect(panel, (255, 255, 255, 34), panel.get_rect(), 1, border_radius=6)
        x = 20; y = HEIGHT - 180
        self.screen.blit(panel, (x, y))
        dist = self.fonts["bold"].render(f"Afstand {self.last_hit_distance:.0f} ft", True, (255, 236, 120))
        self.screen.blit(dist, (x+18, y+16))
        metric = self.fonts["small"].render(
            f"{self.last_hit_distance * 0.3048:.0f} m | {self.last_hit_type} | {self.last_exit_velo:.0f} mph EV",
            True, (218, 226, 238)
        )
        self.screen.blit(metric, (x+18, y+54))

    # ── Game Over screen ──────────────────────────────────────────────────────
    def draw_game_over(self, now):
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((8, 10, 18, 210))
        self.screen.blit(overlay, (0, 0))

        win  = self.player_score > self.cpu_score
        draw = self.player_score == self.cpu_score
        if win:
            title_text  = "GEWONNEN!"
            title_color = (255, 230, 80)
        elif draw:
            title_text  = "GELIJKSPEL"
            title_color = (200, 200, 200)
        else:
            title_text  = "VERLOREN"
            title_color = (255, 90, 90)

        title_surf = self.fonts["huge"].render(title_text, True, title_color)
        self.screen.blit(title_surf, title_surf.get_rect(center=(WIDTH//2, 180)))

        score_surf = self.fonts["big"].render(
            f"JIJ {self.player_score}  –  CPU {self.cpu_score}", True, (240, 244, 255)
        )
        self.screen.blit(score_surf, score_surf.get_rect(center=(WIDTH//2, 268)))

        # Box-score grid
        self.draw_box_score(WIDTH//2, 330)

        # Stats summary
        stats = self.stats
        avg_str = f"{stats.avg:.3f}".lstrip("0") or ".000"
        stat_lines = [
            f"AVG {avg_str}  |  {stats.hits} hits  |  {stats.home_runs} HR  |  {stats.rbi} RBI",
            f"Walks: {stats.walks}  |  Strikeouts: {stats.strikeouts}  |  Beste reeks: {self.streak_best}",
            f"Max exit velo: {stats.max_exit_velo:.0f} mph  |  Langste slag: {stats.max_distance:.0f} ft ({stats.max_distance*0.3048:.0f} m)",
        ]
        for i, line in enumerate(stat_lines):
            surf = self.fonts["body"].render(line, True, (200, 215, 235))
            self.screen.blit(surf, surf.get_rect(center=(WIDTH//2, 490 + i*38)))

        restart = self.fonts["bold"].render("Druk R om opnieuw te spelen  |  ESC om te sluiten", True, (160, 175, 195))
        self.screen.blit(restart, restart.get_rect(center=(WIDTH//2, 630)))

    def draw_box_score(self, cx, y):
        """Simple inning-by-inning score table."""
        col_w = 42
        innings_shown = min(MAX_INNINGS, len(self.inning_scores))
        total_w = (innings_shown + 2) * col_w + 60  # +2 for R totals
        x0 = cx - total_w // 2

        header_bg = pygame.Surface((total_w, 28), pygame.SRCALPHA)
        header_bg.fill((30, 40, 55, 200))
        self.screen.blit(header_bg, (x0, y))

        # Header row
        for i in range(innings_shown):
            s = self.fonts["small"].render(str(i+1), True, (180, 190, 210))
            self.screen.blit(s, s.get_rect(center=(x0 + 50 + i*col_w, y+14)))
        r_s = self.fonts["small"].render("R", True, (255, 220, 80))
        self.screen.blit(r_s, r_s.get_rect(center=(x0 + 50 + innings_shown*col_w + 20, y+14)))

        # Team rows
        row_labels = ["JIJ", "CPU"]
        for row_idx, label in enumerate(row_labels):
            ry = y + 28 + row_idx * 26
            row_bg = pygame.Surface((total_w, 26), pygame.SRCALPHA)
            row_bg.fill((20, 28, 42, 180) if row_idx == 0 else (16, 22, 34, 180))
            self.screen.blit(row_bg, (x0, ry))
            lbl = self.fonts["small"].render(label, True, (220, 228, 240))
            self.screen.blit(lbl, (x0 + 6, ry+5))
            total = 0
            for i, inn in enumerate(self.inning_scores):
                val = inn[row_idx]
                total += val
                color = (255, 220, 80) if val > 0 else (160, 165, 180)
                s = self.fonts["small"].render(str(val), True, color)
                self.screen.blit(s, s.get_rect(center=(x0 + 50 + i*col_w, ry+13)))
            ts = self.fonts["bold"].render(str(total), True, (255, 230, 100))
            self.screen.blit(ts, ts.get_rect(center=(x0 + 50 + innings_shown*col_w + 20, ry+13)))


# ─── Entry point ──────────────────────────────────────────────────────────────
def main():
    pygame.mixer.pre_init(44100, -16, 1, 512)
    game = Game()
    game.run()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pygame.quit()
        sys.exit(0)