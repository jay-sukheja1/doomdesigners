import pygame
import random
import sys
import os
import math
from enum import Enum

# Check for Pillow library for GIF support
try:
    from PIL import Image

    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False
    print("Warning: Pillow library not found. Run 'pip install Pillow' for animations.")

# --- PRE-INITIALIZE MIXER ---
pygame.mixer.pre_init(44100, -16, 2, 512)
pygame.init()
pygame.mixer.init()

# =============================================================================
# CONTROLLER SETUP & RUMBLE LOGIC
# =============================================================================
pygame.joystick.init()
joystick = None

if pygame.joystick.get_count() > 0:
    try:
        joystick = pygame.joystick.Joystick(0)
        joystick.init()
        print(f"✅ Controller Connected: {joystick.get_name()}")
    except Exception as e:
        print(f"❌ Error connecting to controller: {e}")
else:
    print("⚠️ No controller found. Using Keyboard.")


def trigger_rumble(low_freq, high_freq, duration_ms):
    """Triggers haptic feedback if controller is connected."""
    if joystick:
        try:
            joystick.rumble(low_freq, high_freq, duration_ms)
        except AttributeError:
            pass


# =============================================================================
# SMART INPUT WRAPPER (Maps Controller to Keyboard Keys)
# =============================================================================
original_get_pressed = pygame.key.get_pressed

# State trackers for controller inputs
last_start_state = 0
last_a_state = 0
last_hat_x = 0
last_hat_y = 0


class SmartKeyWrapper:
    def __init__(self, real_keys):
        self.real_keys = real_keys
        self.overrides = {}

    def __getitem__(self, key):
        if key in self.overrides:
            return self.overrides[key]
        try:
            return self.real_keys[key]
        except IndexError:
            return 0

    def __setitem__(self, key, value):
        self.overrides[key] = value


def patched_get_pressed():
    global last_start_state, last_a_state
    global last_hat_x, last_hat_y

    real_keys = original_get_pressed()
    keys = SmartKeyWrapper(real_keys)

    if joystick:
        # --- 1. MOVEMENT ---
        axis_x = joystick.get_axis(0)
        axis_y = joystick.get_axis(1)
        hat_x = joystick.get_hat(0)[0] if joystick.get_numhats() > 0 else 0
        hat_y = joystick.get_hat(0)[1] if joystick.get_numhats() > 0 else 0

        # Move Left/Right
        if axis_x < -0.5 or hat_x == -1:
            keys[pygame.K_LEFT] = 1
            keys[pygame.K_a] = 1
        elif axis_x > 0.5 or hat_x == 1:
            keys[pygame.K_RIGHT] = 1
            keys[pygame.K_d] = 1

        # Crouch
        if axis_y > 0.5 or hat_y == -1:
            keys[pygame.K_DOWN] = 1
            keys[pygame.K_s] = 1

        # --- 2. JUMP (Button A / 0) ---
        current_a = joystick.get_button(0)
        if current_a:
            keys[pygame.K_SPACE] = 1
            keys[pygame.K_w] = 1

        # Menu Select (A Button also acts as Enter)
        if current_a and not last_a_state:
            pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
        last_a_state = current_a

        # --- 3. SHOOT (Button X or R2) ---
        # Button 2 (X on Xbox) or Axis 5 (Right Trigger)
        btn_x_pressed = joystick.get_button(2)
        r2_value = joystick.get_axis(5)
        r2_pressed = r2_value > -0.5

        if btn_x_pressed or r2_pressed:
            keys[pygame.K_x] = 1
            keys[pygame.K_LALT] = 1

        # --- 4. UPGRADE SELECTION (D-PAD) ---
        # Only inject these events if we are in upgrade menu (handled by game logic listening to keys)
        if hat_x == -1 and last_hat_x != -1:
            pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_1))  # Left Upgrade
        if hat_x == 1 and last_hat_x != 1:
            pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_3))  # Right Upgrade
        if hat_y == 1 and last_hat_y != 1:
            pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_2))  # Up Upgrade

        last_hat_x = hat_x
        last_hat_y = hat_y

    return keys


# APPLY THE INPUT PATCH
pygame.key.get_pressed = patched_get_pressed

# =============================================================================
# CONSTANTS & GAME SETTINGS
# =============================================================================

SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720
FPS = 90

BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
GRAY = (100, 100, 100)
DARK_GRAY = (50, 50, 50)
LIGHT_GRAY = (150, 150, 150)
RED = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE = (0, 100, 255)
YELLOW = (255, 255, 0)
ORANGE = (255, 165, 0)
PURPLE = (200, 0, 200)
CYAN = (0, 255, 255)
GOLD = (255, 215, 0)
MAGENTA = (255, 0, 255)
MENU_Highlight = (0, 255, 128)

MAX_HEALTH = 100
HEALTH_RESTORE_AMOUNT = 20
LOOT_THRESHOLD = 8
MASK_TARGET = 3  # Level 1 Target
RED_MASK_TARGET = 10  # Level 2 Target

# Combo Constants
COMBO_TIMEOUT = 3.0

# Music Constants
MUSIC_FILE = "Community Beat 2.mp3"
VOL_MENU = 0.6
VOL_GAME = 0.2


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def load_gif_frames(filename, size, transparent_bg=False):
    """
    Loads GIF frames.
    If transparent_bg is True, it automatically detects the top-left pixel color
    and removes it from all frames to create transparency.
    """
    default_surface = pygame.Surface(size)
    default_surface.fill(BLUE)

    if not HAS_PILLOW:
        return [default_surface]

    frames = []
    try:
        if not os.path.exists(filename):
            print(f"Warning: Asset {filename} not found.")
            return [default_surface]

        pil_image = Image.open(filename)
        while True:
            # Convert to RGBA
            frame = pil_image.copy().convert("RGBA")
            data = frame.tobytes()
            mode = frame.mode
            size_img = frame.size

            py_image = pygame.image.fromstring(data, size_img, mode)
            py_image = pygame.transform.scale(py_image, size)

            # --- AUTO TRANSPARENCY FIX ---
            if transparent_bg:
                # Get the color of the top-left pixel (assumed background)
                bg_color = py_image.get_at((0, 0))
                # Set that color as the transparent colorkey
                py_image.set_colorkey(bg_color)

            frames.append(py_image)
            pil_image.seek(pil_image.tell() + 1)
    except EOFError:
        pass
    except FileNotFoundError:
        return [default_surface]
    except Exception as e:
        print(f"Error loading {filename}: {e}")
        return [default_surface]

    return frames if frames else [default_surface]


# =============================================================================
# ENUMS
# =============================================================================

class GameState(Enum):
    MENU = 1
    CONTROLS_GUIDE = 2
    PLAYING = 3
    PAUSED = 4
    UPGRADE_SELECTION = 5
    GAME_OVER = 6
    LEVEL_TRANSITION = 7
    BOSS_TRANSITION = 8
    ANIMATED_LEVEL_TRANSITION = 9
    VICTORY = 10


class UpgradeType(Enum):
    SPEED = "Speed Boost"
    DAMAGE = "Increased Damage"
    ARMOR = "Armor Plating"
    SHIELD = "Temporary Shield"
    ATTACK_SPEED = "Faster Attacks"
    MAX_HEALTH = "Increased Max Health"
    LOOT_BONUS = "Better Healing"


# =============================================================================
# VISUAL EFFECTS
# =============================================================================

class DamageText:
    def __init__(self, x, y, damage, color=WHITE):
        self.x = x
        self.y = y
        self.damage = damage
        self.life = 40
        self.color = color
        self.font = pygame.font.Font(None, 36)
        self.image = self.font.render(str(damage), True, color)
        self.vy = -2

    def update(self):
        self.y += self.vy
        self.life -= 1

    def draw(self, screen, camera_x):
        if self.life > 0:
            draw_pos = (self.x - camera_x, self.y)
            screen.blit(self.image, draw_pos)


class Particle:
    def __init__(self, x, y, color, velocity=(0, 0)):
        self.x, self.y, self.color, self.vx, self.vy = x, y, color, velocity[0], velocity[1]
        self.life, self.size = 30, random.randint(2, 6)

    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.vy += 0.3
        self.life -= 1

    def draw(self, screen, camera_x):
        if self.life > 0:
            alpha = int(255 * (self.life / 30))
            surf = pygame.Surface((self.size * 2, self.size * 2), pygame.SRCALPHA)
            pygame.draw.circle(surf, (*self.color[:3], alpha), (self.size, self.size), self.size)
            screen.blit(surf, (int(self.x - camera_x), int(self.y)))


# =============================================================================
# PLAYER CLASS
# =============================================================================

class Player(pygame.sprite.Sprite):
    def __init__(self, x, y):
        super().__init__()
        self.width = 100
        self.height = 120
        self.facing_right = True
        self.is_shooting = False
        self.is_crouching = False
        self.base_speed = 6
        self.speed_multiplier = 1.0
        self.base_damage = 25
        self.damage_multiplier = 1.0
        self.damage_reduction = 0.0
        self.attack_cooldown = 0
        self.base_attack_cooldown = 30
        self.shield_active = False
        self.shield_duration = 0
        self.vel_y = 0
        self.gravity = 0.8
        self.jump_power = -18
        self.on_ground = False
        self.has_assault_rifle = False
        self.load_assets(1)
        self.image = self.frames[0]
        self.rect = self.image.get_rect()
        self.rect.x = x
        self.rect.y = y

    def load_assets(self, level):
        if level == 1:
            self.frames_right = load_gif_frames("lvl1_r.gif", (self.width, self.height))
            self.frames_left = load_gif_frames("lvl1_l.gif", (self.width, self.height))
            self.frames_shoot_right = load_gif_frames("lvl1_right_shoot2.gif", (self.width, self.height))
            self.frames_shoot_left = load_gif_frames("lvl1_left_shoot2.gif", (self.width, self.height))
        elif level >= 2:
            self.frames_right = load_gif_frames("lvl1_r.gif", (self.width, self.height))
            self.frames_left = load_gif_frames("lvl1_l.gif", (self.width, self.height))
            self.frames_shoot_right = load_gif_frames("lvl1_right_shoot2.gif", (self.width, self.height))
            self.frames_shoot_left = load_gif_frames("lvl1_left_shoot2.gif", (self.width, self.height))

        self.frames = self.frames_right if self.facing_right else self.frames_left
        self.current_frame_index = 0.0
        self.animation_speed = 0.25

    def equip_assault_rifle(self):
        self.has_assault_rifle = True
        self.base_attack_cooldown = 15

    def update(self, keys_pressed):
        move_speed = int(self.base_speed * self.speed_multiplier)
        is_moving = False

        if (keys_pressed[pygame.K_DOWN] or keys_pressed[pygame.K_s]) and self.on_ground:
            self.is_crouching = True
            move_speed = int(move_speed * 0.5)
        else:
            self.is_crouching = False

        if keys_pressed[pygame.K_RIGHT] or keys_pressed[pygame.K_d]:
            self.rect.x += move_speed
            self.facing_right = True
            is_moving = True
        elif keys_pressed[pygame.K_LEFT] or keys_pressed[pygame.K_a]:
            self.rect.x -= move_speed
            self.facing_right = False
            is_moving = True

        if self.is_shooting:
            if self.facing_right:
                self.frames = self.frames_shoot_right
            else:
                self.frames = self.frames_shoot_left
            anim_mult = 2.0 if self.has_assault_rifle else 1.0
            self.current_frame_index += self.animation_speed * anim_mult
            if self.current_frame_index >= len(self.frames):
                self.is_shooting = False
                self.current_frame_index = 0
                self.frames = self.frames_right if self.facing_right else self.frames_left
        else:
            self.frames = self.frames_right if self.facing_right else self.frames_left
            if is_moving:
                self.current_frame_index += self.animation_speed
                if self.current_frame_index >= len(self.frames): self.current_frame_index = 0
            else:
                self.current_frame_index = 0

        idx = int(self.current_frame_index)
        current_frame = self.frames[idx] if idx < len(self.frames) else self.frames[0]

        if self.is_crouching:
            new_height = int(self.height * 0.6)
            self.image = pygame.transform.scale(current_frame, (self.width, new_height))
            if self.rect.height != new_height:
                bottom_pos = self.rect.bottom
                self.rect.height = new_height
                self.rect.bottom = bottom_pos
        else:
            self.image = current_frame
            if self.rect.height != self.height:
                bottom_pos = self.rect.bottom
                self.rect.height = self.height
                self.rect.bottom = bottom_pos

        if (keys_pressed[pygame.K_w] or keys_pressed[pygame.K_SPACE]) and self.on_ground and not self.is_crouching:
            self.vel_y = self.jump_power
            self.on_ground = False

        self.vel_y += self.gravity
        self.rect.y += int(self.vel_y)
        ground_level = SCREEN_HEIGHT - 150
        if self.rect.bottom >= ground_level:
            self.rect.bottom = ground_level
            self.vel_y = 0
            self.on_ground = True

        if self.rect.top < 0: self.rect.top = 0
        if self.rect.x < 0: self.rect.x = 0
        if self.attack_cooldown > 0: self.attack_cooldown -= 1
        if self.shield_duration > 0:
            self.shield_duration -= 1
        else:
            self.shield_active = False

    def attack(self):
        if self.attack_cooldown == 0:
            self.attack_cooldown = self.base_attack_cooldown
            self.is_shooting = True
            self.current_frame_index = 0

            # --- CONTROLLER VIBRATION ON SHOOT ---
            trigger_rumble(1.0, 1.0, 150)

            return True
        return False

    def get_damage(self):
        damage = int(self.base_damage * self.damage_multiplier)
        if self.is_crouching:
            damage = int(damage * 0.6)
        return damage

    def activate_shield(self, duration=300):
        self.shield_active = True
        self.shield_duration = duration

    def draw(self, screen, camera_x):
        draw_x = self.rect.x - camera_x
        draw_y = self.rect.bottom - self.image.get_height()
        if self.shield_active:
            shield_surface = pygame.Surface((self.rect.width + 20, self.rect.height + 20), pygame.SRCALPHA)
            shield_alpha = int(128 + 127 * (self.shield_duration % 20) / 20)
            pygame.draw.ellipse(shield_surface, (*CYAN, shield_alpha),
                                (0, 0, self.rect.width + 20, self.rect.height + 20), 3)
            screen.blit(shield_surface, (draw_x - 10, draw_y - 10))
        screen.blit(self.image, (draw_x, draw_y))


# =============================================================================
# BOSS CLASSES
# =============================================================================

# --- LEVEL 1 BOSS ---
class GlitchMerchantBoss(pygame.sprite.Sprite):
    def __init__(self, x, y):
        super().__init__()
        self.width, self.height = 150, 150
        self.max_health = 250
        self.health = self.max_health
        self.damage, self.speed = 12, 2.5
        self.frames = load_gif_frames("boss.gif", (self.width, self.height))
        self.anim_index = 0
        self.anim_speed = 0.2
        self.image = self.frames[0]
        self.rect = self.image.get_rect()
        self.rect.x, self.rect.y = x, y
        self.base_y = y
        self.phase = 1
        self.attack_timer = 0
        self.attack_cooldown = 150
        self.movement_timer = 0
        self.teleport_cooldown = 0
        self.glitch_particles = []
        self.corruption_bullets = []
        self.hit_flash = 0
        self.phase_2_health = self.max_health * 0.66
        self.phase_3_health = self.max_health * 0.33

    def update(self, player_rect):
        if self.health <= self.phase_3_health and self.phase < 3:
            self.phase = 3
            self.attack_cooldown = 100
        elif self.health <= self.phase_2_health and self.phase < 2:
            self.phase = 2
            self.attack_cooldown = 130
        self.anim_index += self.anim_speed
        if self.anim_index >= len(self.frames): self.anim_index = 0
        self.image = self.frames[int(self.anim_index)]
        self.movement_timer += 1
        self.rect.y = self.base_y + math.sin(self.movement_timer * 0.05) * 25
        target_dist = 450
        if self.phase == 2: target_dist = 350
        if self.phase == 3: target_dist = 250
        target_x = player_rect.right + target_dist
        target_x += math.cos(self.movement_timer * 0.04) * 30
        if self.phase == 3: target_x += math.sin(self.movement_timer * 0.1) * 40
        if self.rect.x < target_x:
            self.rect.x += self.speed
        elif self.rect.x > target_x + 20:
            self.rect.x -= self.speed

        if self.phase >= 2:
            if self.teleport_cooldown > 0: self.teleport_cooldown -= 1
            should_teleport = (self.rect.x - player_rect.right < 100) and (random.random() < 0.02)
            if self.teleport_cooldown == 0 and should_teleport: self.teleport(player_rect)
        self.attack_timer += 1
        if self.attack_timer >= self.attack_cooldown:
            self.attack(player_rect)
            self.attack_timer = 0
        for particle in self.glitch_particles[:]:
            particle['life'] -= 1
            particle['x'] += particle['vx']
            particle['y'] += particle['vy']
            if particle['life'] <= 0: self.glitch_particles.remove(particle)
        for bullet in self.corruption_bullets[:]:
            bullet['x'] += bullet['vx']
            bullet['y'] += bullet['vy']
            bullet['life'] -= 1
            if bullet['life'] <= 0: self.corruption_bullets.remove(bullet)
        if self.hit_flash > 0: self.hit_flash -= 1

    def attack(self, player_rect):
        if self.phase == 1:
            self.shoot_corruption_bullet(player_rect, spread=0, count=1)
        elif self.phase == 2:
            self.shoot_corruption_bullet(player_rect, spread=15, count=2)
        else:
            self.shoot_corruption_bullet(player_rect, spread=20, count=3)

    def shoot_corruption_bullet(self, player_rect, spread=0, count=1):
        start_x, start_y = self.rect.centerx, self.rect.centery
        dx, dy = player_rect.centerx - start_x, player_rect.centery - start_y
        angle = math.atan2(dy, dx)
        for i in range(count):
            offset_angle = angle + math.radians(spread * (i - (count - 1) / 2))
            speed = 7
            vx = math.cos(offset_angle) * speed
            vy = math.sin(offset_angle) * speed
            bullet = {'x': start_x, 'y': start_y, 'vx': vx, 'vy': vy, 'life': 120,
                      'color': random.choice([(0, 255, 255), (255, 0, 255), (0, 255, 100)])}
            self.corruption_bullets.append(bullet)

    def teleport(self, player_rect):
        self.rect.x = player_rect.right + random.randint(300, 600)
        self.teleport_cooldown = 180
        for _ in range(20): self.spawn_glitch_particle()

    def spawn_glitch_particle(self):
        particle = {'x': self.rect.centerx + random.randint(-50, 50),
                    'y': self.rect.centery + random.randint(-50, 50),
                    'vx': random.uniform(-2, 2), 'vy': random.uniform(-2, 2),
                    'life': 30, 'color': random.choice([(0, 255, 255), (255, 0, 255), (0, 255, 100)]),
                    'size': random.randint(3, 8)}
        self.glitch_particles.append(particle)

    def take_damage(self, damage):
        self.health -= damage
        self.hit_flash = 5
        return self.health <= 0

    def draw(self, screen, camera_x):
        draw_x, draw_y = self.rect.x - camera_x, self.rect.y
        for particle in self.glitch_particles:
            px, py = int(particle['x'] - camera_x), int(particle['y'])
            alpha = int(255 * (particle['life'] / 30))
            surf = pygame.Surface((particle['size'] * 2, particle['size'] * 2), pygame.SRCALPHA)
            pygame.draw.circle(surf, (*particle['color'], alpha), (particle['size'], particle['size']),
                               particle['size'])
            screen.blit(surf, (px, py))
        if self.hit_flash > 0:
            flash = self.image.copy()
            flash.fill((255, 255, 255, 128), special_flags=pygame.BLEND_ADD)
            screen.blit(flash, (draw_x, draw_y))
        else:
            screen.blit(self.image, (draw_x, draw_y))
        for bullet in self.corruption_bullets:
            bx, by = int(bullet['x'] - camera_x), int(bullet['y'])
            pygame.draw.circle(screen, bullet['color'], (bx, by), 8)
        bar_x, bar_y = draw_x + self.width // 2 - 100, draw_y - 30
        pygame.draw.rect(screen, DARK_GRAY, (bar_x, bar_y, 200, 15))
        pct = max(0, self.health / self.max_health)
        col = (0, 255, 100) if pct > 0.6 else (RED if pct < 0.3 else YELLOW)
        pygame.draw.rect(screen, col, (bar_x, bar_y, int(200 * pct), 15))
        font = pygame.font.Font(None, 24)
        screen.blit(font.render("GLITCH BOSS", True, CYAN), (bar_x, bar_y - 20))


# --- LEVEL 2 BOSS (MECH BOSS) ---
class MechBoss(pygame.sprite.Sprite):
    def __init__(self, x, y, player):
        super().__init__()
        self.width, self.height = 200, 200  # Larger size for the mech
        self.max_health = 600
        self.health = self.max_health
        self.damage = 15
        self.player = player

        # Load assets with transparency (removes background color)
        # Using greatboss.gif as requested
        self.frames = load_gif_frames("greatboss.gif", (self.width, self.height), transparent_bg=True)

        self.anim_index = 0
        self.anim_speed = 0.2
        self.image = self.frames[0]
        self.rect = self.image.get_rect()
        self.rect.x, self.rect.y = x, y

        # Movement vars (Floating style like Lvl 1 Boss)
        self.base_y = y
        self.movement_timer = 0
        self.speed = 2.5

        # Attack Logic
        self.attack_timer = 0
        self.flame_timer = 0

        # Projectiles list (compatible with Game loop check)
        self.corruption_bullets = []
        self.hit_flash = 0

    def update(self, player_rect):
        if self.hit_flash > 0: self.hit_flash -= 1

        # 1. Animation
        self.anim_index += self.anim_speed
        if self.anim_index >= len(self.frames): self.anim_index = 0
        self.image = self.frames[int(self.anim_index)]

        # 2. Movement (Level 1 Style Hover & Chase)
        self.movement_timer += 1
        # Gentle floating on Y axis
        self.rect.y = self.base_y + math.sin(self.movement_timer * 0.05) * 15

        target_dist = 300  # Keep some distance
        target_x = player_rect.right + target_dist

        # Smooth follow x
        if self.rect.x < target_x:
            self.rect.x += self.speed
        elif self.rect.x > target_x + 20:
            self.rect.x -= self.speed

        # 3. Attacks
        dist_to_player = math.hypot(player_rect.centerx - self.rect.centerx, player_rect.centery - self.rect.centery)

        if dist_to_player < 350:  # NEAR - FLAMES
            if self.flame_timer <= 0:
                self.fire_flames()
                self.flame_timer = 5  # Rapid fire flames
            else:
                self.flame_timer -= 1
        else:  # FAR - BULLETS
            if self.attack_timer <= 0:
                self.shoot_bullet()
                self.attack_timer = 60  # Slower fire rate for bullets
            else:
                self.attack_timer -= 1

        # Update Projectiles
        for bullet in self.corruption_bullets[:]:
            bullet['x'] += bullet['vx']
            bullet['y'] += bullet['vy']
            bullet['life'] -= 1
            if bullet['life'] <= 0: self.corruption_bullets.remove(bullet)

    def fire_flames(self):
        # Cone of fire towards player
        start_x, start_y = self.rect.centerx - 40, self.rect.centery + 20
        dx = self.player.rect.centerx - start_x
        dy = self.player.rect.centery - start_y
        angle = math.atan2(dy, dx)

        # Spread
        angle += random.uniform(-0.3, 0.3)
        speed = random.uniform(5, 8)
        vx = math.cos(angle) * speed
        vy = math.sin(angle) * speed

        flame = {
            'x': start_x, 'y': start_y,
            'vx': vx, 'vy': vy,
            'life': 40,
            'color': random.choice([ORANGE, RED, YELLOW]),
            'size': random.randint(5, 10)
        }
        self.corruption_bullets.append(flame)

    def shoot_bullet(self):
        start_x, start_y = self.rect.centerx - 50, self.rect.centery
        dx = self.player.rect.centerx - start_x
        dy = self.player.rect.centery - start_y
        angle = math.atan2(dy, dx)

        speed = 10
        vx = math.cos(angle) * speed
        vy = math.sin(angle) * speed

        bullet = {
            'x': start_x, 'y': start_y,
            'vx': vx, 'vy': vy,
            'life': 100,
            'color': CYAN,
            'size': 8
        }
        self.corruption_bullets.append(bullet)

    def take_damage(self, damage):
        self.health -= damage
        self.hit_flash = 5
        return self.health <= 0

    def draw(self, screen, camera_x):
        draw_x, draw_y = self.rect.x - camera_x, self.rect.y

        if self.hit_flash > 0:
            flash = self.image.copy()
            flash.fill((255, 255, 255, 128), special_flags=pygame.BLEND_ADD)
            screen.blit(flash, (draw_x, draw_y))
        else:
            screen.blit(self.image, (draw_x, draw_y))

        # Draw Projectiles
        for bullet in self.corruption_bullets:
            bx, by = int(bullet['x'] - camera_x), int(bullet['y'])
            pygame.draw.circle(screen, bullet['color'], (bx, by), bullet['size'])

        # Health Bar
        bar_x, bar_y = draw_x + self.width // 2 - 100, draw_y - 30
        pygame.draw.rect(screen, DARK_GRAY, (bar_x, bar_y, 200, 15))
        pct = max(0, self.health / self.max_health)
        col = (0, 255, 100) if pct > 0.6 else (RED if pct < 0.3 else YELLOW)
        pygame.draw.rect(screen, col, (bar_x, bar_y, int(200 * pct), 15))
        font = pygame.font.Font(None, 24)
        screen.blit(font.render("MECH TITAN", True, RED), (bar_x, bar_y - 20))


# =============================================================================
# PROJECTILES & ENEMIES
# =============================================================================

class Projectile(pygame.sprite.Sprite):
    def __init__(self, x, y, damage, direction, max_distance=400):
        super().__init__()
        self.width, self.height = 20, 10
        base_image = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        base_image.fill(YELLOW)
        pygame.draw.circle(base_image, ORANGE, (15, 5), 4)
        self.image = pygame.transform.flip(base_image, True, False) if direction == -1 else base_image
        self.rect = self.image.get_rect()
        self.rect.x, self.rect.y = x, y
        self.direction = direction
        self.speed = 12 * self.direction
        self.damage = damage
        self.distance_traveled = 0
        self.max_distance = max_distance

    def update(self):
        self.rect.x += self.speed
        self.distance_traveled += abs(self.speed)
        if self.distance_traveled > self.max_distance: self.kill()

    def draw(self, screen, camera_x):
        screen.blit(self.image, (self.rect.x - camera_x, self.rect.y))


class Enemy(pygame.sprite.Sprite):
    def __init__(self, x, y, enemy_type="basic", is_pothole=False, difficulty_multiplier=1.0):
        super().__init__()
        self.enemy_type = enemy_type
        self.is_pothole = is_pothole
        if enemy_type == "fast":
            self.width, self.height, self.speed = 50, 80, 3
            self.max_health = int(40 * difficulty_multiplier)
            self.damage, self.color = 12, RED
        elif enemy_type == "tank":
            self.width, self.height, self.speed = 100, 140, 1
            self.max_health = int(80 * difficulty_multiplier)
            self.damage, self.color = 20, PURPLE
        else:
            self.width, self.height, self.speed = 80, 110, 2
            self.max_health = int(50 * difficulty_multiplier)
            self.damage, self.color = 15, ORANGE
        self.anim_index = 0
        self.anim_speed = 0.2
        if self.is_pothole:
            raw_frames = load_gif_frames("zombie_underground.gif", (self.width, self.height))
            self.frames = []
            self.peek_height = int(self.height * 0.5)
            for frame in raw_frames:
                cropped = frame.subsurface(pygame.Rect(0, 0, self.width, self.peek_height)).copy()
                self.frames.append(cropped)
            self.image = self.frames[0]
            self.speed = 0
            self.rect = self.image.get_rect()
            self.rect.x, self.rect.y = x, y
        else:
            self.frames_l = load_gif_frames("zombie_l.gif", (self.width, self.height))
            self.frames_r = load_gif_frames("zombie_r.gif", (self.width, self.height))
            self.frames = self.frames_r
            self.image = self.frames[0]
            self.rect = self.image.get_rect()
            self.rect.x = x
            self.rect.y = y - (self.height - 55)
        self.start_x = x
        self.patrol_range = 100
        self.patrol_dir = 1
        self.health = self.max_health
        self.hit_flash = 0

    def update(self):
        self.anim_index += self.anim_speed
        if self.is_pothole:
            if self.anim_index >= len(self.frames): self.anim_index = 0
            self.image = self.frames[int(self.anim_index)]
        else:
            self.rect.x += self.speed * self.patrol_dir
            if self.rect.x > self.start_x + self.patrol_range:
                self.patrol_dir = -1
            elif self.rect.x < self.start_x - self.patrol_range:
                self.patrol_dir = 1
            current_frames = self.frames_r if self.patrol_dir == 1 else self.frames_l
            if self.anim_index >= len(current_frames): self.anim_index = 0
            self.image = current_frames[int(self.anim_index)]
        if self.hit_flash > 0: self.hit_flash -= 1

    def take_damage(self, damage):
        self.health -= damage
        self.hit_flash = 5
        return self.health <= 0

    def draw(self, screen, camera_x):
        draw_x = self.rect.x - camera_x
        draw_y = self.rect.y
        if draw_x < -100 or draw_x > SCREEN_WIDTH + 100: return
        if self.is_pothole:
            hole_rect = pygame.Rect(draw_x + 2, draw_y + self.rect.height - 10, self.width - 4, 16)
            pygame.draw.ellipse(screen, (20, 20, 20), hole_rect)
        if self.hit_flash > 0:
            flash_surface = self.image.copy()
            flash_surface.fill((255, 255, 255), special_flags=pygame.BLEND_ADD)
            screen.blit(flash_surface, (draw_x, draw_y))
        else:
            screen.blit(self.image, (draw_x, draw_y))
        bar_y = draw_y - 10
        pygame.draw.rect(screen, DARK_GRAY, (draw_x, bar_y, self.width, 5))
        health_percent = self.health / self.max_health
        if health_percent < 0: health_percent = 0
        health_color = GREEN if health_percent > 0.5 else (YELLOW if health_percent > 0.25 else RED)
        pygame.draw.rect(screen, health_color, (draw_x, bar_y, int(self.width * health_percent), 5))


class MutatedZombie(pygame.sprite.Sprite):
    def __init__(self, x, y, player, is_pothole=False, difficulty_multiplier=1.0):
        super().__init__()
        self.player = player
        self.is_pothole = is_pothole
        self.enemy_type = "mutated"
        self.width, self.height = 80, 110
        self.speed = 3
        self.max_health = int(60 * difficulty_multiplier)
        self.health = self.max_health
        self.damage = 18
        self.color = (100, 0, 100)
        self.anim_index = 0
        self.anim_speed = 0.2
        self.hit_flash = 0
        self.patrol_dir = 1
        self.start_x = x
        self.patrol_range = 100
        self.facing_right = True

        self.load_mutated_assets()

        if self.is_pothole:
            self.image = self.frames_pothole[0]
            self.rect = self.image.get_rect()
            self.rect.x, self.rect.y = x, y
        else:
            self.image = self.frames_run_r[0]
            self.rect = self.image.get_rect()
            self.rect.x = x
            self.rect.y = y - (self.height - 55)

    def load_mutated_assets(self):
        size = (self.width, self.height)
        if self.is_pothole:
            raw_frames = load_gif_frames("A_fast_mutated_humanoid_enemy_for_a_2D_pixel_art_s_rotations_4dir.gif", size)
            self.frames_pothole = []
            self.peek_height = int(self.height * 0.5)
            for frame in raw_frames:
                cropped = frame.subsurface(pygame.Rect(0, 0, self.width, self.peek_height)).copy()
                self.frames_pothole.append(cropped)
        else:
            self.frames_run_r = load_gif_frames(
                "A_fast_mutated_humanoid_enemy_for_a_2D_pixel_art_s_running-6-frames_east.gif", size)
            self.frames_run_l = load_gif_frames("output-onlinegiftools (1).gif", size)
            self.frames_punch_r = load_gif_frames(
                "A_fast_mutated_humanoid_enemy_for_a_2D_pixel_art_s_cross-punch_east.gif", size)
            self.frames_punch_l = load_gif_frames(
                "A_fast_mutated_humanoid_enemy_for_a_2D_pixel_art_s_cross-punch_west.gif", size)

    def update(self):
        if self.hit_flash > 0: self.hit_flash -= 1

        if self.is_pothole:
            self.anim_index += self.anim_speed
            if self.anim_index >= len(self.frames_pothole): self.anim_index = 0
            self.image = self.frames_pothole[int(self.anim_index)]
        else:
            dist_x = self.player.rect.centerx - self.rect.centerx
            distance = abs(dist_x)

            if distance < 80:
                self.anim_speed = 0.25
                if dist_x > 0:
                    current_frames = self.frames_punch_r
                    self.facing_right = True
                else:
                    current_frames = self.frames_punch_l
                    self.facing_right = False
            else:
                self.anim_speed = 0.2
                self.rect.x += self.speed * self.patrol_dir
                if self.rect.x > self.start_x + self.patrol_range:
                    self.patrol_dir = -1
                elif self.rect.x < self.start_x - self.patrol_range:
                    self.patrol_dir = 1

                if self.patrol_dir == 1:
                    current_frames = self.frames_run_r
                else:
                    current_frames = self.frames_run_l

            self.anim_index += self.anim_speed
            if self.anim_index >= len(current_frames): self.anim_index = 0
            self.image = current_frames[int(self.anim_index)]

    def take_damage(self, damage):
        self.health -= damage
        self.hit_flash = 5
        return self.health <= 0

    def draw(self, screen, camera_x):
        draw_x = self.rect.x - camera_x
        draw_y = self.rect.y
        if draw_x < -100 or draw_x > SCREEN_WIDTH + 100: return

        if self.is_pothole:
            hole_rect = pygame.Rect(draw_x + 2, draw_y + self.rect.height - 10, self.width - 4, 16)
            pygame.draw.ellipse(screen, (20, 20, 20), hole_rect)

        if self.hit_flash > 0:
            flash_surface = self.image.copy()
            flash_surface.fill((255, 255, 255), special_flags=pygame.BLEND_ADD)
            screen.blit(flash_surface, (draw_x, draw_y))
        else:
            screen.blit(self.image, (draw_x, draw_y))

        bar_y = draw_y - 10
        pygame.draw.rect(screen, DARK_GRAY, (draw_x, bar_y, self.width, 5))
        health_percent = self.health / self.max_health
        if health_percent < 0: health_percent = 0
        health_color = GREEN if health_percent > 0.5 else (YELLOW if health_percent > 0.25 else RED)
        pygame.draw.rect(screen, health_color, (draw_x, bar_y, int(self.width * health_percent), 5))


class ZombieDog(Enemy):
    def __init__(self, x, y, player, difficulty_multiplier=1.0):
        pygame.sprite.Sprite.__init__(self)
        self.player = player
        self.enemy_type = "dog"
        self.is_pothole = False
        self.width = 90
        self.height = 60
        self.speed_patrol = 2
        self.speed_chase = 6
        self.damage = 10
        self.color = (139, 69, 19)
        self.max_health = int(35 * difficulty_multiplier)
        self.health = self.max_health
        self.load_dog_assets()
        self.image = self.frames_walk_r[0]
        self.rect = self.image.get_rect()
        self.rect.x = x
        self.rect.y = y - (self.height - 50)
        self.start_x = x
        self.patrol_range = 150
        self.patrol_dir = 1
        self.hit_flash = 0
        self.anim_index = 0
        self.anim_speed = 0.2
        self.state = "PATROL"
        self.facing_right = True

    def load_dog_assets(self):
        size = (self.width, self.height)
        self.frames_walk_r = load_gif_frames(
            "A_mutated_zombie_dog_enemy_for_a_2D_pixel_art_side_walk-6-frames_east.gif", size)
        self.frames_walk_l = [pygame.transform.flip(f, True, False) for f in self.frames_walk_r]
        self.frames_run_r = load_gif_frames(
            "A_mutated_zombie_dog_enemy_for_a_2D_pixel_art_side_running-6-frames_east.gif", size)
        self.frames_run_l = load_gif_frames(
            "A_mutated_zombie_dog_enemy_for_a_2D_pixel_art_side_running-6-frames_west.gif", size)
        self.frames_jump_l = load_gif_frames("A_mutated_zombie_dog_enemy_for_a_2D_pixel_art_side_jump_west.gif", size)
        self.frames_jump_r = [pygame.transform.flip(f, True, False) for f in self.frames_jump_l]

    def update(self):
        dist_x = self.player.rect.centerx - self.rect.centerx
        distance = abs(dist_x)
        current_frames = self.frames_walk_r

        if distance < 500:
            self.state = "CHASE"
        else:
            self.state = "PATROL"

        if self.state == "CHASE":
            if dist_x > 0:
                self.rect.x += self.speed_chase
                self.facing_right = True
                current_frames = self.frames_run_r
            else:
                self.rect.x -= self.speed_chase
                self.facing_right = False
                current_frames = self.frames_run_l

            if distance < 100:
                current_frames = self.frames_jump_r if self.facing_right else self.frames_jump_l
                self.anim_speed = 0.3
            else:
                self.anim_speed = 0.25

        elif self.state == "PATROL":
            self.anim_speed = 0.15
            self.rect.x += self.speed_patrol * self.patrol_dir
            if self.rect.x > self.start_x + self.patrol_range:
                self.patrol_dir = -1
                self.facing_right = False
            elif self.rect.x < self.start_x - self.patrol_range:
                self.patrol_dir = 1
                self.facing_right = True

            current_frames = self.frames_walk_r if self.facing_right else self.frames_walk_l

        self.anim_index += self.anim_speed
        if self.anim_index >= len(current_frames):
            self.anim_index = 0

        self.image = current_frames[int(self.anim_index)]

        if self.hit_flash > 0:
            self.hit_flash -= 1


# =============================================================================
# COLLECTIBLES
# =============================================================================

class Loot(pygame.sprite.Sprite):
    def __init__(self, x, y, value_multiplier=1.0):
        super().__init__()
        self.size = 35
        self.value_multiplier = value_multiplier
        self.image = pygame.Surface((self.size, self.size))
        self.image.fill(GREEN)
        pygame.draw.circle(self.image, YELLOW, (self.size // 2, self.size // 2), 8)
        if os.path.exists("heartloot.jpg"):
            try:
                original_img = pygame.image.load("heartloot.jpg").convert()
                self.image = pygame.transform.scale(original_img, (self.size, self.size))
                self.image.set_colorkey((255, 255, 255))
            except Exception as e:
                print(f"Error loading loot image: {e}")
        self.rect = self.image.get_rect()
        self.rect.x, self.rect.y = x, y
        self.float_timer, self.vel_y, self.gravity = 0, -5, 0.3

    def update(self):
        self.vel_y += self.gravity
        self.rect.y += int(self.vel_y)
        self.float_timer += 0.15
        if self.rect.bottom >= SCREEN_HEIGHT - 150:
            self.rect.bottom = SCREEN_HEIGHT - 150
            self.vel_y = 0

    def draw(self, screen, camera_x):
        draw_x = self.rect.x - camera_x
        draw_y = self.rect.y + int(pygame.math.Vector2(0, 1).rotate(self.float_timer * 360).y * 2)
        screen.blit(self.image, (draw_x, draw_y))

    def get_restore_value(self):
        return int(HEALTH_RESTORE_AMOUNT * self.value_multiplier)


class Mask(pygame.sprite.Sprite):
    def __init__(self, x, y):
        super().__init__()
        self.size = 35
        if os.path.exists("mask.jpg"):
            self.image = pygame.image.load("mask.jpg").convert_alpha()
            self.image = pygame.transform.scale(self.image, (self.size, self.size))
        else:
            self.image = pygame.Surface((self.size, self.size), pygame.SRCALPHA)
            pygame.draw.ellipse(self.image, (220, 220, 220), (0, 0, self.size, self.size))
            pygame.draw.circle(self.image, BLACK, (10, 12), 4)
            pygame.draw.circle(self.image, BLACK, (25, 12), 4)
            pygame.draw.circle(self.image, (100, 100, 100), (17, 25), 2)
            pygame.draw.circle(self.image, (100, 100, 100), (12, 28), 2)
            pygame.draw.circle(self.image, (100, 100, 100), (22, 28), 2)
        self.rect = self.image.get_rect()
        self.rect.x, self.rect.y = x, y
        self.float_timer, self.vel_y, self.gravity = 0, -5, 0.3

    def update(self):
        self.vel_y += self.gravity
        self.rect.y += int(self.vel_y)
        self.float_timer += 0.1
        if self.rect.bottom >= SCREEN_HEIGHT - 150:
            self.rect.bottom = SCREEN_HEIGHT - 150
            self.vel_y = 0

    def draw(self, screen, camera_x):
        draw_x = self.rect.x - camera_x
        draw_y = self.rect.y + int(pygame.math.Vector2(0, 1).rotate(self.float_timer * 360).y * 3)
        screen.blit(self.image, (draw_x, draw_y))


class RedMask(Mask):
    """ Same as Mask but tinted Red for Level 2 """

    def __init__(self, x, y):
        super().__init__(x, y)
        # Create a red tint
        tinted = self.image.copy()
        tinted.fill((255, 50, 50), special_flags=pygame.BLEND_MULT)
        self.image = tinted


# =============================================================================
# UPGRADE SYSTEM
# =============================================================================

class Upgrade:
    def __init__(self, upgrade_type, description, apply_func):
        self.name = upgrade_type.value
        self.description = description
        self.apply_func = apply_func

    def apply(self, game):
        self.apply_func(game)


class UpgradeManager:
    @staticmethod
    def get_random_upgrades(count=3):
        all_upgrades = [
            Upgrade(UpgradeType.SPEED, "Move 25% faster",
                    lambda g: setattr(g.player, 'speed_multiplier', g.player.speed_multiplier * 1.25)),
            Upgrade(UpgradeType.DAMAGE, "Deal 50% more damage",
                    lambda g: setattr(g.player, 'damage_multiplier', g.player.damage_multiplier * 1.5)),
            Upgrade(UpgradeType.ARMOR, "Take 20% less damage",
                    lambda g: setattr(g.player, 'damage_reduction', min(0.8, g.player.damage_reduction + 0.2))),
            Upgrade(UpgradeType.SHIELD, "Gain a shield for 10 seconds", lambda g: g.player.activate_shield(600)),
            Upgrade(UpgradeType.ATTACK_SPEED, "Attack 40% faster",
                    lambda g: setattr(g.player, 'base_attack_cooldown', int(g.player.base_attack_cooldown * 0.6))),
            Upgrade(UpgradeType.MAX_HEALTH, "Increase max health by 25",
                    lambda g: (setattr(g, 'max_health', g.max_health + 25),
                               setattr(g, 'current_health', g.current_health + 25))),
            Upgrade(UpgradeType.LOOT_BONUS, "Heal 50% more from loot",
                    lambda g: setattr(g, 'loot_multiplier', g.loot_multiplier * 1.5)),
        ]
        return random.sample(all_upgrades, min(count, len(all_upgrades)))


# =============================================================================
# GAME MANAGER
# =============================================================================

class Game:
    def __init__(self):
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption("Veil Runner - Enhanced Controller Edition")
        self.clock = pygame.time.Clock()
        self.state = GameState.MENU
        self.running = True

        self.score, self.high_score, self.loot_count = 0, 0, 0
        self.kills, self.mask_count = 0, 0
        self.red_mask_count = 0  # NEW LEVEL 2 COUNTER
        self.level = 1
        self.max_health, self.current_health = MAX_HEALTH, MAX_HEALTH
        self.loot_multiplier = 1.0

        # Combo Variables
        self.combo = 0
        self.last_kill_time = 0

        self.camera_x = 0
        self.difficulty_multiplier = 1.0
        self.next_spawn_x = 800

        self.all_sprites = pygame.sprite.Group()
        self.enemies = pygame.sprite.Group()
        self.loots = pygame.sprite.Group()
        self.masks = pygame.sprite.Group()
        self.projectiles = pygame.sprite.Group()
        self.damage_texts = []
        self.player = None
        self.particles = []
        self.available_upgrades = []

        self.boss = None
        self.boss_active = False

        # --- TRANSITION VARIABLES ---
        self.boss_arena_locked = False
        self.boss_arena_left_bound = 0
        self.boss_arena_right_bound = 0
        self.player_left_bound = 0
        self.player_right_bound = 0
        self.boss_transition_timer = 0
        self.boss_transition_phase = 0
        self.level_transition_timer = 0

        self.font_large = pygame.font.Font(None, 72)
        self.font_medium = pygame.font.Font(None, 48)
        self.font_small = pygame.font.Font(None, 36)
        self.font_tiny = pygame.font.Font(None, 24)

        # Assets
        if os.path.exists("final_back2.jpg"):
            self.bg_lvl1 = pygame.image.load("final_back2.jpg").convert()
            self.bg_lvl1 = pygame.transform.scale(self.bg_lvl1, (SCREEN_WIDTH, SCREEN_HEIGHT))
        else:
            self.bg_lvl1 = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
            self.bg_lvl1.fill((20, 20, 30))

        if os.path.exists("level2_bg.jpg"):
            self.bg_lvl2 = pygame.image.load("level2_bg.jpg").convert()
            self.bg_lvl2 = pygame.transform.scale(self.bg_lvl2, (SCREEN_WIDTH, SCREEN_HEIGHT))
        else:
            self.bg_lvl2 = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
            self.bg_lvl2.fill((50, 0, 0))

        # Boss Arena Background
        if os.path.exists("boss_arena.jpg"):
            self.bg_boss_arena = pygame.image.load("boss_arena.jpg").convert()
            self.bg_boss_arena = pygame.transform.scale(self.bg_boss_arena, (SCREEN_WIDTH, SCREEN_HEIGHT))
        else:
            self.bg_boss_arena = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
            self.bg_boss_arena.fill((10, 5, 15))
            for i in range(50):
                x = random.randint(0, SCREEN_WIDTH)
                y = random.randint(0, SCREEN_HEIGHT)
                size = random.randint(1, 3)
                pygame.draw.circle(self.bg_boss_arena, (50, 20, 60), (x, y), size)

        self.current_bg = self.bg_lvl1

        if os.path.exists("platform.jpg"):
            self.platform_image = pygame.image.load("platform.jpg").convert()
        else:
            self.platform_image = None

        # Upgrade Icons
        icon_size = (50, 50)
        self.icon_left, self.icon_up, self.icon_right = None, None, None
        if os.path.exists("left.jpeg"): self.icon_left = pygame.transform.scale(
            pygame.image.load("left.jpeg").convert(), icon_size)
        if os.path.exists("up.jpeg"): self.icon_up = pygame.transform.scale(pygame.image.load("up.jpeg").convert(),
                                                                            icon_size)
        if os.path.exists("right.jpeg"): self.icon_right = pygame.transform.scale(
            pygame.image.load("right.jpeg").convert(), icon_size)

        # Sounds
        self.snd_shoot, self.snd_hit, self.snd_collect = None, None, None
        if os.path.exists("Shoot9.wav"): self.snd_shoot = pygame.mixer.Sound("Shoot9.wav")
        if os.path.exists("Hit11.wav"): self.snd_hit = pygame.mixer.Sound("Hit11.wav")
        if os.path.exists("Blip1.wav"): self.snd_collect = pygame.mixer.Sound("Blip1.wav")

        # --- MUSIC LOADING ---
        if os.path.exists(MUSIC_FILE):
            try:
                pygame.mixer.music.load(MUSIC_FILE)
                pygame.mixer.music.play(-1)
                pygame.mixer.music.set_volume(VOL_MENU)
            except Exception as e:
                print(f"Could not load music: {e}")
        else:
            print(f"Warning: {MUSIC_FILE} not found.")

        # Menu System
        self.menu_options = ["START GAME", "HOW TO PLAY", "EXIT"]
        self.menu_selection = 0

        # Transition Data (for static transitions)
        self.trans_title = ""
        self.trans_subtitle = ""
        self.trans_hint = ""
        self.trans_callback = None

    def trigger_transition(self, title, subtitle, hint, callback):
        self.state = GameState.LEVEL_TRANSITION
        self.trans_title = title
        self.trans_subtitle = subtitle
        self.trans_hint = hint
        self.trans_callback = callback

    # --- NEW ANIMATED TRANSITIONS ---

    def start_boss_transition(self):
        self.state = GameState.BOSS_TRANSITION
        self.boss_transition_timer = 0
        self.boss_transition_phase = 0
        self.boss_arena_left_bound = self.camera_x
        self.boss_arena_right_bound = self.camera_x + SCREEN_WIDTH * 2
        self.player_left_bound = self.camera_x
        self.player_right_bound = self.camera_x + SCREEN_WIDTH

    def update_boss_transition(self):
        self.boss_transition_timer += 1
        if self.boss_transition_timer == 60:
            self.boss_transition_phase = 1
        elif self.boss_transition_timer == 180:
            self.boss_transition_phase = 2
        elif self.boss_transition_timer == 240:
            if self.level == 1:
                self.spawn_level1_boss()
            elif self.level == 2:
                self.spawn_level2_boss()
            self.state = GameState.PLAYING
            self.boss_transition_timer = 0

    def draw_boss_transition(self):
        if self.boss_transition_timer < 60:
            alpha = int((self.boss_transition_timer / 60) * 255)
            fade_surf = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
            fade_surf.fill(BLACK)
            fade_surf.set_alpha(alpha)
            self.draw_background()
            self.player.draw(self.screen, self.camera_x)
            self.screen.blit(fade_surf, (0, 0))

        elif self.boss_transition_timer < 180:
            self.screen.fill(BLACK)
            glitch_offset = random.randint(-5, 5) if random.random() < 0.3 else 0
            text_timer = self.boss_transition_timer - 60

            if text_timer > 20:
                text1 = self.font_large.render("COLLECTION COMPLETE", True, GOLD)
                self.screen.blit(text1, (SCREEN_WIDTH // 2 - text1.get_width() // 2 + glitch_offset, 150))

            if text_timer > 70:
                warning = self.font_medium.render("⚠ WARNING ⚠", True, RED)
                pulse = abs(math.sin(text_timer * 0.1)) * 0.3 + 0.7
                warning.set_alpha(int(255 * pulse))
                self.screen.blit(warning, (SCREEN_WIDTH // 2 - warning.get_width() // 2, 330))

            if text_timer > 90:
                boss_name = "GLITCH MERCHANT" if self.level == 1 else "MECH TITAN"
                boss_text = self.font_large.render(f"{boss_name} APPROACHING", True, MAGENTA)
                self.screen.blit(boss_text, (SCREEN_WIDTH // 2 - boss_text.get_width() // 2 + glitch_offset, 420))

        else:
            alpha = int(255 - ((self.boss_transition_timer - 180) / 60) * 255)
            self.screen.blit(self.bg_boss_arena, (0, 0))
            if self.boss_transition_timer == 180:
                self.player.rect.x = self.boss_arena_left_bound + 100
                self.camera_x = self.boss_arena_left_bound
            self.player.draw(self.screen, self.camera_x)
            fade_surf = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
            fade_surf.fill(BLACK)
            fade_surf.set_alpha(alpha)
            self.screen.blit(fade_surf, (0, 0))

    def start_level_transition(self):
        self.state = GameState.ANIMATED_LEVEL_TRANSITION
        self.level_transition_timer = 0
        self.boss_arena_locked = False
        self.boss_active = False
        self.boss = None

    def update_level_transition(self):
        self.level_transition_timer += 1
        if self.level_transition_timer >= 180:
            self.advance_level()

    def draw_level_transition(self):
        timer = self.level_transition_timer
        if timer < 60:
            self.screen.blit(self.bg_boss_arena, (0, 0))
            self.player.draw(self.screen, self.camera_x)
            victory = self.font_large.render("BOSS DEFEATED!", True, GOLD)
            self.screen.blit(victory, (SCREEN_WIDTH // 2 - victory.get_width() // 2, SCREEN_HEIGHT // 2 - 50))
        elif timer < 120:
            self.screen.fill(BLACK)
            alpha = int(((timer - 60) / 60) * 255)
            if self.level == 1:
                text1 = self.font_medium.render("Leaving the Docks...", True, CYAN)
            else:
                text1 = self.font_medium.render("Mission Complete!", True, GOLD)
            text1.set_alpha(alpha)
            self.screen.blit(text1, (SCREEN_WIDTH // 2 - text1.get_width() // 2, SCREEN_HEIGHT // 2 - 40))
        else:
            # End of transition logic
            pass

    def advance_level(self):
        if self.level == 1:
            self.level = 2
            self.current_bg = self.bg_lvl2
            self.player.load_assets(2)
            self.create_particles(self.player.rect.centerx, self.player.rect.centery, GOLD, 100)
            self.difficulty_multiplier = 2.0
            self.camera_x = self.boss_arena_right_bound
            self.next_spawn_x = self.camera_x + 800
            self.state = GameState.PLAYING
            self.player.equip_assault_rifle()
            # Reset mask count for level 2 logic, but keep total masks separate?
            # Actually we use red_mask_count for lvl 2
            self.red_mask_count = 0
        elif self.level == 2:
            self.state = GameState.VICTORY

    def start_game_sequence(self):
        self.reset_game_data()
        self.trigger_transition("LEVEL 1", "The Outskirts", "HINT: Collect 3 Masks to summon the Boss!",
                                self.begin_gameplay)

    def begin_gameplay(self):
        self.state = GameState.PLAYING
        pygame.mixer.music.set_volume(VOL_GAME)

    def reset_game_data(self):
        self.all_sprites.empty()
        self.enemies.empty()
        self.loots.empty()
        self.masks.empty()
        self.projectiles.empty()
        self.particles.clear()
        self.damage_texts.clear()
        self.boss = None
        self.boss_active = False
        self.player = Player(100, SCREEN_HEIGHT - 200)
        self.all_sprites.add(self.player)
        self.camera_x = 0
        self.score, self.loot_count = 0, 0
        self.kills, self.mask_count = 0, 0
        self.red_mask_count = 0
        self.level = 1
        self.current_bg = self.bg_lvl1
        self.current_health = MAX_HEALTH
        self.difficulty_multiplier = 1.0
        self.next_spawn_x = 800
        self.max_health = MAX_HEALTH
        self.loot_multiplier = 1.0
        self.combo = 0
        self.last_kill_time = 0
        self.boss_arena_locked = False
        self.boss_transition_timer = 0
        self.level_transition_timer = 0

    def spawn_level1_boss(self):
        self.boss_active = True
        self.boss_arena_locked = True
        self.current_bg = self.bg_boss_arena
        boss_x = self.boss_arena_right_bound - 300
        boss_y = SCREEN_HEIGHT - 250
        self.boss = GlitchMerchantBoss(boss_x, boss_y)
        self.all_sprites.add(self.boss)
        for e in self.enemies: e.kill()
        self.state = GameState.PLAYING

    def spawn_level2_boss(self):
        self.boss_active = True
        self.boss_arena_locked = True
        self.current_bg = self.bg_boss_arena
        boss_x = self.boss_arena_right_bound - 300
        boss_y = SCREEN_HEIGHT - 280
        self.boss = MechBoss(boss_x, boss_y, self.player)
        self.all_sprites.add(self.boss)
        for e in self.enemies: e.kill()
        self.state = GameState.PLAYING

    def spawn_world_chunk(self):
        if self.boss_active: return
        spawn_x_start = self.next_spawn_x
        num_enemies = random.randint(1, 3)
        current_chunk_width = 0
        ground_level = SCREEN_HEIGHT - 160
        for i in range(num_enemies):
            ex = spawn_x_start + current_chunk_width
            is_pothole_spawn = random.choice([True, False])
            if is_pothole_spawn:
                ey = ground_level - 20
                is_pothole = True
            else:
                ey = ground_level - 55
                is_pothole = False

            if self.level >= 2:
                # 20% Chance for Dog, 80% Chance for Mutated Zombie
                if random.random() < 0.2:
                    spawn_dog = True
                    spawn_mutated = False
                else:
                    spawn_dog = False
                    spawn_mutated = True
            else:
                spawn_dog = False
                spawn_mutated = False

            if spawn_dog:
                ey = ground_level - 30
                enemy = ZombieDog(ex, ey, self.player, self.difficulty_multiplier)
            elif spawn_mutated:
                if is_pothole:
                    ey = ground_level - 20
                else:
                    ey = ground_level - 55
                enemy = MutatedZombie(ex, ey, self.player, is_pothole, self.difficulty_multiplier)
            else:
                enemy_type = random.choice(["basic", "basic", "fast", "tank"])
                enemy = Enemy(ex, ey, enemy_type, is_pothole, self.difficulty_multiplier)

            self.enemies.add(enemy)
            self.all_sprites.add(enemy)
            gap = 400 + random.randint(0, 150)
            current_chunk_width += gap
        self.next_spawn_x += current_chunk_width + 100

    def spawn_loot(self, x, y):
        if self.level == 1 and self.mask_count < MASK_TARGET:
            if random.random() < 0.15:
                mask = Mask(x, y)
                self.masks.add(mask)
                self.all_sprites.add(mask)
                return

        # Level 2 Masks are spawned specifically by Dogs in combat loop

        if random.random() < 0.6:
            loot = Loot(x, y, self.loot_multiplier)
            self.loots.add(loot)
            self.all_sprites.add(loot)

    def spawn_red_mask(self, x, y):
        mask = RedMask(x, y)
        self.masks.add(mask)
        self.all_sprites.add(mask)

    def spawn_projectile(self):
        if self.player.facing_right:
            proj_x, direction = self.player.rect.right, 1
        else:
            proj_x, direction = self.player.rect.left - 20, -1
        proj_y = self.player.rect.centery - 5
        current_range = 900 if self.player.is_crouching else 400
        proj = Projectile(proj_x, proj_y, self.player.get_damage(), direction, current_range)
        self.projectiles.add(proj)
        self.all_sprites.add(proj)
        if self.snd_shoot: self.snd_shoot.play()

    def create_particles(self, x, y, color, count=10):
        for _ in range(count):
            self.particles.append(Particle(x, y, color, (random.uniform(-4, 4), random.uniform(-6, -2))))

    def spawn_damage_text(self, x, y, damage, color=WHITE):
        self.damage_texts.append(DamageText(x, y, damage, color))

    def handle_combat(self):
        player_hitbox = self.player.rect.inflate(-50, -20)
        current_time = pygame.time.get_ticks() / 1000.0

        for proj in self.projectiles:
            for enemy in self.enemies:
                enemy_hitbox = enemy.rect.inflate(-20, -10)
                if proj.rect.colliderect(enemy_hitbox):
                    if self.snd_hit: self.snd_hit.play()
                    damage = proj.damage
                    if self.combo > 1: damage = int(damage * (1 + (self.combo * 0.1)))
                    self.spawn_damage_text(enemy.rect.centerx, enemy.rect.top, damage, ORANGE)
                    if enemy.take_damage(damage):
                        self.create_particles(enemy.rect.centerx, enemy.rect.centery, enemy.color, 15)

                        # --- LEVEL 2 RED MASK DROP LOGIC ---
                        if self.level == 2 and enemy.enemy_type == "dog":
                            # Guaranteed drop or high chance for Red Mask
                            self.spawn_red_mask(enemy.rect.centerx, enemy.rect.centery)
                        else:
                            self.spawn_loot(enemy.rect.centerx, enemy.rect.centery)

                        if current_time - self.last_kill_time < COMBO_TIMEOUT:
                            self.combo += 1
                        else:
                            self.combo = 1
                        self.last_kill_time = current_time
                        base_score = 50
                        combo_bonus = int(base_score * (self.combo * 0.5))
                        self.score += base_score + combo_bonus
                        self.kills += 1
                        enemy.kill()
                    proj.kill();
                    break

            if self.boss and proj.alive():
                boss_hitbox = self.boss.rect.inflate(-40, -40)
                if proj.rect.colliderect(boss_hitbox):
                    if self.snd_hit: self.snd_hit.play()
                    damage = proj.damage
                    if self.combo > 1: damage = int(damage * (1 + (self.combo * 0.1)))
                    self.spawn_damage_text(self.boss.rect.centerx, self.boss.rect.top, damage, RED)
                    if self.boss.take_damage(damage):
                        self.create_particles(self.boss.rect.centerx, self.boss.rect.centery, GOLD, 50)
                        self.score += 5000
                        self.kills += 1
                        self.boss.kill()
                        self.start_level_transition()
                    proj.kill()

        for enemy in self.enemies:
            enemy_hitbox = enemy.rect.inflate(-40, -20)
            if enemy_hitbox.colliderect(player_hitbox):
                if not self.player.shield_active:
                    raw_damage = enemy.damage
                    actual_damage = int(raw_damage * (1.0 - self.player.damage_reduction))
                    self.current_health -= actual_damage
                    self.create_particles(self.player.rect.centerx, self.player.rect.centery, RED, 10)
                    self.player.rect.x -= 30
                    self.combo = 0
                else:
                    self.create_particles(enemy.rect.centerx, enemy.rect.centery, CYAN, 10)
                enemy.kill()

        if self.boss:
            boss_hitbox = self.boss.rect.inflate(-50, -50)
            if boss_hitbox.colliderect(player_hitbox):
                if not self.player.shield_active:
                    self.player.rect.x -= 20
                    self.current_health -= 1
                    self.combo = 0
                else:
                    self.player.rect.x -= 20

    def handle_collections(self):
        player_hitbox = self.player.rect.inflate(-50, -20)
        for loot in self.loots:
            if loot.rect.colliderect(player_hitbox):
                if self.snd_collect: self.snd_collect.play()
                heal_val = loot.get_restore_value()
                self.current_health = min(self.max_health, self.current_health + heal_val)
                self.loot_count += 1
                self.create_particles(loot.rect.centerx, loot.rect.centery, GREEN, 8)
                loot.kill()
                if self.loot_count >= LOOT_THRESHOLD:
                    self.loot_count = 0
                    self.available_upgrades = UpgradeManager.get_random_upgrades(3)
                    self.state = GameState.UPGRADE_SELECTION

        for mask in self.masks:
            if mask.rect.colliderect(player_hitbox):
                if self.snd_collect: self.snd_collect.play()

                # Check if it's a red mask (Level 2)
                if isinstance(mask, RedMask):
                    self.red_mask_count += 1
                    self.create_particles(mask.rect.centerx, mask.rect.centery, RED, 15)
                else:
                    self.mask_count += 1
                    self.create_particles(mask.rect.centerx, mask.rect.centery, GOLD, 12)

                mask.kill()

                # Check triggers
                if self.level == 1 and self.mask_count >= MASK_TARGET:
                    if not self.boss_active:
                        self.start_boss_transition()
                elif self.level == 2 and self.red_mask_count >= RED_MASK_TARGET:
                    if not self.boss_active:
                        self.start_boss_transition()

    def update_playing(self, keys_pressed):
        was_alive = (self.state == GameState.PLAYING)

        self.player.update(keys_pressed)
        current_time = pygame.time.get_ticks() / 1000.0
        if current_time - self.last_kill_time > COMBO_TIMEOUT: self.combo = 0

        target_camera_x = self.player.rect.x - 200
        if target_camera_x < 0: target_camera_x = 0
        if target_camera_x > self.camera_x: self.camera_x += (target_camera_x - self.camera_x) * 0.1
        if self.player.rect.x < self.camera_x: self.player.rect.x = self.camera_x

        if self.camera_x + SCREEN_WIDTH > self.next_spawn_x and not self.boss_arena_locked:
            self.spawn_world_chunk()
            self.difficulty_multiplier += 0.05

        if self.boss:
            self.boss.update(self.player.rect)
            # Projectile Logic for Level 1 Boss
            if hasattr(self.boss, 'corruption_bullets'):
                player_hitbox = self.player.rect.inflate(-50, -20)
                for bullet in self.boss.corruption_bullets:
                    # Treat Flames and Bullets similarly for collision
                    bullet_rect = pygame.Rect(bullet['x'] - bullet.get('size', 8), bullet['y'] - bullet.get('size', 8),
                                              bullet.get('size', 8) * 2, bullet.get('size', 8) * 2)
                    if bullet_rect.colliderect(player_hitbox):
                        if not self.player.shield_active:
                            damage_val = 15
                            if bullet.get('type') == 'flame':
                                damage_val = 5  # Flames tick faster but less damage per tick? Or same.
                            self.current_health -= damage_val
                            self.create_particles(self.player.rect.centerx, self.player.rect.centery, RED, 5)
                            self.combo = 0
                        self.boss.corruption_bullets.remove(bullet)

        if self.current_health <= 0:
            self.current_health = 0
            self.state = GameState.GAME_OVER
            if self.score > self.high_score: self.high_score = self.score

        if keys_pressed[pygame.K_LALT] and self.player.attack(): self.spawn_projectile()

        self.enemies.update()
        self.projectiles.update()
        self.loots.update()
        self.masks.update()
        for p in self.particles[:]:
            p.update()
            if p.life <= 0: self.particles.remove(p)
        for dt in self.damage_texts[:]:
            dt.update()
            if dt.life <= 0: self.damage_texts.remove(dt)

        self.handle_combat()
        self.handle_collections()

        # --- CONTROLLER RUMBLE ON DEATH ---
        if was_alive and self.state == GameState.GAME_OVER:
            trigger_rumble(1.0, 1.0, 1000)

    def draw_background(self):
        rel_x = int(self.camera_x * 0.5) % SCREEN_WIDTH
        self.screen.blit(self.current_bg, (-rel_x, 0))
        if rel_x > 0: self.screen.blit(self.current_bg, (SCREEN_WIDTH - rel_x, 0))
        ground_y = SCREEN_HEIGHT - 170
        if self.platform_image:
            platform_width = self.platform_image.get_width()
            cam_offset = int(self.camera_x % platform_width)
            start_x = -cam_offset
            for i in range(start_x, SCREEN_WIDTH, platform_width): self.screen.blit(self.platform_image, (i, ground_y))
        else:
            pygame.draw.rect(self.screen, LIGHT_GRAY, (0, ground_y, SCREEN_WIDTH, 150))
            for i in range(0, SCREEN_WIDTH, 30): pygame.draw.rect(self.screen, (120, 100, 80),
                                                                  (i + 5, ground_y + 30, 20, 120))
            pygame.draw.line(self.screen, WHITE, (0, ground_y), (SCREEN_WIDTH, ground_y), 3)

    def draw_radar(self):
        radar_w, radar_h, radar_x, radar_y = 200, 100, SCREEN_WIDTH - 220, 20
        pygame.draw.rect(self.screen, (0, 30, 0), (radar_x, radar_y, radar_w, radar_h))
        pygame.draw.rect(self.screen, GREEN, (radar_x, radar_y, radar_w, radar_h), 2)
        scale_x, scale_y = radar_w / (SCREEN_WIDTH * 1.5), radar_h / SCREEN_HEIGHT
        px_rel, py_rel = (self.player.rect.centerx - self.camera_x) * scale_x, self.player.rect.centery * scale_y
        if 0 <= px_rel <= radar_w: pygame.draw.circle(self.screen, CYAN, (radar_x + int(px_rel), radar_y + int(py_rel)),
                                                      3)
        for enemy in self.enemies:
            ex_rel, ey_rel = (enemy.rect.centerx - self.camera_x) * scale_x, enemy.rect.centery * scale_y
            if 0 <= ex_rel <= radar_w: pygame.draw.circle(self.screen, RED,
                                                          (radar_x + int(ex_rel), radar_y + int(ey_rel)), 3)
        if self.boss:
            bx_rel, by_rel = (self.boss.rect.centerx - self.camera_x) * scale_x, self.boss.rect.centery * scale_y
            if 0 <= bx_rel <= radar_w: pygame.draw.circle(self.screen, PURPLE,
                                                          (radar_x + int(bx_rel), radar_y + int(by_rel)), 6)

    def draw_combo_meter(self):
        if self.combo > 1:
            combo_x, combo_y = SCREEN_WIDTH // 2 - 100, 80
            pulse = abs(pygame.time.get_ticks() % 500 - 250) / 250.0
            combo_size = int(48 + pulse * 12)
            combo_font = pygame.font.Font(None, combo_size)
            combo_text = combo_font.render(f"{self.combo}x COMBO!", True, YELLOW)
            text_rect = combo_text.get_rect(center=(SCREEN_WIDTH // 2, combo_y))
            shadow = combo_font.render(f"{self.combo}x COMBO!", True, BLACK)
            self.screen.blit(shadow, (text_rect.x + 3, text_rect.y + 3))
            self.screen.blit(combo_text, text_rect)
            bar_width, bar_height, bar_x, bar_y = 200, 10, SCREEN_WIDTH // 2 - 100, combo_y + 30
            pygame.draw.rect(self.screen, DARK_GRAY, (bar_x, bar_y, bar_width, bar_height))
            time_remaining = max(0, COMBO_TIMEOUT - (pygame.time.get_ticks() / 1000.0 - self.last_kill_time))
            fill_width = int((time_remaining / COMBO_TIMEOUT) * bar_width)
            color = GREEN if time_remaining > 1.5 else (YELLOW if time_remaining > 0.5 else RED)
            pygame.draw.rect(self.screen, color, (bar_x, bar_y, fill_width, bar_height))
            pygame.draw.rect(self.screen, WHITE, (bar_x, bar_y, bar_width, bar_height), 2)

    def draw_ui(self):
        pygame.draw.rect(self.screen, DARK_GRAY, (20, 20, 300, 30))
        pct = max(0, self.current_health / self.max_health)
        bar_color = GREEN if pct > 0.6 else (YELLOW if pct > 0.3 else RED)
        pygame.draw.rect(self.screen, bar_color, (20, 20, int(300 * pct), 30))
        self.screen.blit(
            self.font_tiny.render(f"HEALTH: {int(self.current_health)}/{int(self.max_health)}", True, WHITE), (30, 25))
        self.screen.blit(self.font_small.render(f"Level: {self.level}", True, CYAN), (20, 100))
        self.screen.blit(self.font_small.render(f"Score: {self.score}", True, WHITE), (20, 140))
        self.screen.blit(self.font_small.render(f"Kills: {self.kills}", True, RED), (20, 180))
        if self.player.has_assault_rifle: self.screen.blit(self.font_small.render("WEAPON: ASSAULT RIFLE", True, GOLD),
                                                           (20, 60))
        self.screen.blit(self.font_small.render(f"Hearts: {self.loot_count}/{LOOT_THRESHOLD}", True, GREEN), (20, 220))

        # UI for Masks
        if self.level == 1:
            mask_color = GOLD if self.mask_count >= MASK_TARGET else YELLOW
            status_text = "BOSS FIGHT!" if self.boss_active else f"{self.mask_count}/{MASK_TARGET}"
            self.screen.blit(self.font_small.render(f"Masks: {status_text}", True, mask_color), (20, 260))
        elif self.level == 2:
            mask_color = RED if self.red_mask_count >= RED_MASK_TARGET else ORANGE
            status_text = "BOSS FIGHT!" if self.boss_active else f"{self.red_mask_count}/{RED_MASK_TARGET}"
            self.screen.blit(self.font_small.render(f"Red Masks: {status_text}", True, mask_color), (20, 260))

        self.draw_radar()
        self.draw_combo_meter()

    def draw_main_menu(self):
        self.screen.fill(DARK_GRAY)
        title = self.font_large.render("Veil Runner", True, WHITE)
        self.screen.blit(title, (SCREEN_WIDTH // 2 - title.get_width() // 2, 100))
        for i, option in enumerate(self.menu_options):
            color = MENU_Highlight if i == self.menu_selection else GRAY
            text = self.font_medium.render(option, True, color)
            self.screen.blit(text, (SCREEN_WIDTH // 2 - text.get_width() // 2, 300 + i * 80))
            if i == self.menu_selection:
                pygame.draw.polygon(self.screen, color, [
                    (SCREEN_WIDTH // 2 - text.get_width() // 2 - 40, 310 + i * 80),
                    (SCREEN_WIDTH // 2 - text.get_width() // 2 - 20, 320 + i * 80),
                    (SCREEN_WIDTH // 2 - text.get_width() // 2 - 40, 330 + i * 80)
                ])

    def draw_transition_screen(self):
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 230))
        self.screen.blit(overlay, (0, 0))
        title = self.font_large.render(self.trans_title, True, GOLD)
        subtitle = self.font_medium.render(self.trans_subtitle, True, WHITE)
        hint = self.font_small.render(self.trans_hint, True, CYAN)
        prompt = self.font_tiny.render("PRESS ENTER TO CONTINUE", True, LIGHT_GRAY)
        self.screen.blit(title, (SCREEN_WIDTH // 2 - title.get_width() // 2, 200))
        self.screen.blit(subtitle, (SCREEN_WIDTH // 2 - subtitle.get_width() // 2, 280))
        self.screen.blit(hint, (SCREEN_WIDTH // 2 - hint.get_width() // 2, 400))
        if (pygame.time.get_ticks() // 500) % 2 == 0:
            self.screen.blit(prompt, (SCREEN_WIDTH // 2 - prompt.get_width() // 2, 600))

    def draw_controls_guide(self):
        self.screen.fill(BLACK)
        self.screen.blit(self.bg_lvl1, (0, 0))
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 220))
        self.screen.blit(overlay, (0, 0))
        box_w, box_h = 1000, 600
        box_rect = pygame.Rect((SCREEN_WIDTH - box_w) // 2, (SCREEN_HEIGHT - box_h) // 2, box_w, box_h)
        pygame.draw.rect(self.screen, (30, 30, 40), box_rect)
        pygame.draw.rect(self.screen, CYAN, box_rect, 4)
        title = self.font_large.render("CONTROLLER / KEYBOARD GUIDE", True, YELLOW)
        self.screen.blit(title, (SCREEN_WIDTH // 2 - title.get_width() // 2, box_rect.y + 30))
        headers_y = box_rect.y + 100
        pygame.draw.line(self.screen, GRAY, (box_rect.left + 50, headers_y + 40), (box_rect.right - 50, headers_y + 40),
                         2)
        col1_x = box_rect.left + 100
        col2_x = box_rect.centerx + 50
        self.screen.blit(self.font_medium.render("INPUT", True, ORANGE), (col1_x, headers_y))
        self.screen.blit(self.font_medium.render("ACTION", True, ORANGE), (col2_x, headers_y))
        instructions = [
            ("L-Stick / Arrows", "Move Left/Right"),
            ("Button A / Space", "Jump / Select"),
            ("Button X / L-Alt", "Shoot"),
            ("Stick Down / Down", "Crouch"),
            ("Start / Enter", "Pause / Menu")
        ]
        start_y = headers_y + 70
        row_h = 60
        for i, (inp, act) in enumerate(instructions):
            inp_surf = self.font_small.render(inp, True, CYAN)
            self.screen.blit(inp_surf, (col1_x, start_y + i * row_h))
            act_surf = self.font_small.render(act, True, WHITE)
            self.screen.blit(act_surf, (col2_x, start_y + i * row_h))
            if i < len(instructions) - 1:
                pygame.draw.line(self.screen, (60, 60, 70), (box_rect.left + 50, start_y + i * row_h + 45),
                                 (box_rect.right - 50, start_y + i * row_h + 45), 1)
        footer = self.font_small.render("PRESS ENTER TO RETURN", True, GREEN)
        self.screen.blit(footer, (SCREEN_WIDTH // 2 - footer.get_width() // 2, box_rect.bottom - 60))

    def run(self):
        while self.running:
            keys = pygame.key.get_pressed()
            for event in pygame.event.get():
                if event.type == pygame.QUIT: self.running = False
                if event.type == pygame.KEYDOWN:
                    if self.state == GameState.MENU:
                        if event.key == pygame.K_UP:
                            self.menu_selection = (self.menu_selection - 1) % len(self.menu_options)
                        elif event.key == pygame.K_DOWN:
                            self.menu_selection = (self.menu_selection + 1) % len(self.menu_options)
                        elif event.key == pygame.K_RETURN:
                            if self.menu_selection == 0:
                                self.start_game_sequence()
                            elif self.menu_selection == 1:
                                self.state = GameState.CONTROLS_GUIDE
                            elif self.menu_selection == 2:
                                self.running = False
                    elif self.state == GameState.LEVEL_TRANSITION:
                        if event.key == pygame.K_RETURN:
                            if self.trans_callback:
                                self.trans_callback()
                    elif self.state == GameState.CONTROLS_GUIDE:
                        if event.key == pygame.K_RETURN:
                            self.state = GameState.MENU
                    elif self.state == GameState.GAME_OVER or self.state == GameState.VICTORY:
                        if event.key == pygame.K_RETURN:
                            self.state = GameState.MENU
                            pygame.mixer.music.set_volume(VOL_MENU)
                    elif self.state == GameState.UPGRADE_SELECTION:
                        idx = -1
                        if event.key == pygame.K_LEFT or event.key == pygame.K_1:
                            idx = 0
                        elif event.key == pygame.K_UP or event.key == pygame.K_2:
                            idx = 1
                        elif event.key == pygame.K_RIGHT or event.key == pygame.K_3:
                            idx = 2
                        if idx != -1 and idx < len(self.available_upgrades):
                            self.available_upgrades[idx].apply(self)
                            self.state = GameState.PLAYING

            if self.state == GameState.PLAYING:
                self.update_playing(keys)
            elif self.state == GameState.BOSS_TRANSITION:
                self.update_boss_transition()
            elif self.state == GameState.ANIMATED_LEVEL_TRANSITION:
                self.update_level_transition()

            if self.state == GameState.MENU:
                self.draw_main_menu()
            elif self.state == GameState.LEVEL_TRANSITION:
                if self.level > 0: self.draw_background()
                self.draw_transition_screen()
            elif self.state == GameState.BOSS_TRANSITION:
                self.draw_boss_transition()
            elif self.state == GameState.ANIMATED_LEVEL_TRANSITION:
                self.draw_level_transition()
            elif self.state == GameState.CONTROLS_GUIDE:
                self.draw_controls_guide()
            elif self.state == GameState.PLAYING:
                self.draw_background()
                for e in self.enemies: e.draw(self.screen, self.camera_x)
                for l in self.loots: l.draw(self.screen, self.camera_x)
                for m in self.masks: m.draw(self.screen, self.camera_x)
                if self.boss: self.boss.draw(self.screen, self.camera_x)
                for p in self.projectiles: p.draw(self.screen, self.camera_x)
                self.player.draw(self.screen, self.camera_x)
                for p in self.particles: p.draw(self.screen, self.camera_x)
                for dt in self.damage_texts: dt.draw(self.screen, self.camera_x)
                self.draw_ui()
            elif self.state == GameState.GAME_OVER:
                self.screen.fill(BLACK)
                game_over = self.font_large.render("GAME OVER", True, RED)
                self.screen.blit(game_over, (SCREEN_WIDTH // 2 - game_over.get_width() // 2, 200))
                score = self.font_medium.render(f"Final Score: {self.score}", True, WHITE)
                self.screen.blit(score, (SCREEN_WIDTH // 2 - score.get_width() // 2, 300))
                retry = self.font_small.render("Press ENTER to Return to Menu", True, LIGHT_GRAY)
                self.screen.blit(retry, (SCREEN_WIDTH // 2 - retry.get_width() // 2, 420))
            elif self.state == GameState.VICTORY:
                self.screen.fill(GOLD)
                win = self.font_large.render("YOU WIN!", True, BLACK)
                self.screen.blit(win, (SCREEN_WIDTH // 2 - win.get_width() // 2, 200))
                score = self.font_medium.render(f"Final Score: {self.score}", True, DARK_GRAY)
                self.screen.blit(score, (SCREEN_WIDTH // 2 - score.get_width() // 2, 300))
                retry = self.font_small.render("Press ENTER to Return to Menu", True, BLACK)
                self.screen.blit(retry, (SCREEN_WIDTH // 2 - retry.get_width() // 2, 420))
            elif self.state == GameState.UPGRADE_SELECTION:
                self.draw_background()
                self.player.draw(self.screen, self.camera_x)
                overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
                overlay.fill((0, 0, 0, 200))
                self.screen.blit(overlay, (0, 0))
                dpad_labels = ["◄ LEFT", "▲ UP", "► RIGHT"]
                for i, u in enumerate(self.available_upgrades):
                    x = 100 + i * 400
                    pygame.draw.rect(self.screen, DARK_GRAY, (x, 250, 300, 200))
                    self.screen.blit(self.font_medium.render(u.name, True, WHITE), (x + 20, 270))
                    self.screen.blit(self.font_tiny.render(u.description, True, LIGHT_GRAY), (x + 20, 330))
                    image_to_draw = None
                    if i == 0:
                        image_to_draw = self.icon_left
                    elif i == 1:
                        image_to_draw = self.icon_up
                    elif i == 2:
                        image_to_draw = self.icon_right
                    if image_to_draw:
                        self.screen.blit(image_to_draw, image_to_draw.get_rect(center=(x + 150, 415)))
                    else:
                        self.screen.blit(self.font_medium.render(dpad_labels[i], True, YELLOW), (x + 100, 410))

            pygame.display.flip()
            self.clock.tick(FPS)
        pygame.quit()


if __name__ == "__main__":
    Game().run()