"""Central configuration for the voice-reactive mystical orb.

Every tunable lives here so the rest of the code reads like intent, not magic
numbers. Values are grouped by subsystem.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# --------------------------------------------------------------------------- #
# Window
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class WindowConfig:
    width: int = 720
    height: int = 720
    title: str = "Arcane Orb"
    always_on_top: bool = True
    frameless: bool = True
    transparent: bool = True
    target_fps: int = 60


# --------------------------------------------------------------------------- #
# Audio
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class AudioConfig:
    sample_rate: int = 44100
    block_size: int = 1024
    channels: int = 1
    # Exponential smoothing factor applied to the raw RMS level.
    smoothing: float = 0.15
    # Decay applied to the smoothed level when no fresh audio arrives, so the
    # orb settles gracefully instead of freezing on the last value.
    decay: float = 0.90
    fft_bins: int = 512
    # Gain applied before clamping; tuned so normal speech reaches ~0.6-0.9.
    input_gain: float = 6.0


# --------------------------------------------------------------------------- #
# Colour palette (linear-ish RGB, additively blended)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Palette:
    core_hot: tuple = (1.0, 0.97, 0.82)        # white-gold center
    core_warm: tuple = (1.0, 0.52, 0.08)        # saturated amber
    ring_gold: tuple = (1.0, 0.70, 0.12)        # vivid glyph gold
    ring_deep: tuple = (1.0, 0.38, 0.04)        # deep amber
    energy: tuple = (1.0, 0.64, 0.12)
    background_a: tuple = (0.00, 0.40, 0.34)     # electric teal/green halo
    background_b: tuple = (0.16, 0.05, 0.00)     # warm shadow
    nebula_a: tuple = (0.45, 0.10, 0.30)         # magenta wisp
    nebula_b: tuple = (0.05, 0.30, 0.45)         # cyan-blue wisp
    rays: tuple = (1.0, 0.82, 0.40)
    particles: tuple = (1.0, 0.78, 0.40)


# --------------------------------------------------------------------------- #
# Animation timings (seconds for a full cycle)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Timings:
    outer_ring_period: float = 30.0     # clockwise
    inner_ring_period: float = 45.0     # counter-clockwise
    breathing_period: float = 4.0
    # State transition smoothing time-constant (seconds to ~63% of target).
    state_blend_tau: float = 0.45


# --------------------------------------------------------------------------- #
# Geometry — radii are fractions of the half-viewport (0..1)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Geometry:
    core_radius: float = 0.20
    energy_radius: float = 0.345
    energy_sides: int = 7              # heptagonal energy ring (per reference)
    inner_ring_radius: float = 0.44
    inner_ring_width: float = 0.090   # thick band so characters show full height
    outer_ring_radius: float = 0.64
    outer_ring_width: float = 0.100
    background_radius: float = 0.98
    ray_count: int = 110
    line_count: int = 40              # crisp full-width radial filaments
    glyph_count_inner: int = 20       # fewer = larger, legible characters
    glyph_count_outer: int = 28


# --------------------------------------------------------------------------- #
# Particles
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ParticleConfig:
    max_particles: int = 4096
    base_emission: float = 30.0        # particles / second when idle
    speaking_emission: float = 900.0   # additional rate scaled by audio
    base_speed: float = 0.06
    speed_audio_gain: float = 0.22
    min_life: float = 1.2
    max_life: float = 3.4
    size_min: float = 2.0
    size_max: float = 7.0


# --------------------------------------------------------------------------- #
# Post processing
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class PostConfig:
    bloom_threshold: float = 0.62
    bloom_intensity_idle: float = 0.85
    bloom_intensity_gain: float = 0.9      # extra scaled by audio
    bloom_downsample: int = 2              # render bloom at 1/N resolution
    chromatic_base: float = 0.0012
    chromatic_gain: float = 0.004


# --------------------------------------------------------------------------- #
# Per-state reactive parameters. These are blended smoothly at runtime.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class StateParams:
    glow_intensity: float = 1.0
    rotation_mult: float = 1.0
    energy_turbulence: float = 0.05
    ray_intensity: float = 0.25
    ray_length: float = 0.35
    particle_activity: float = 0.0
    flash_rate: float = 0.0          # micro-flashes / second
    ripple_strength: float = 0.0


STATE_PRESETS = {
    "IDLE": StateParams(
        glow_intensity=1.15,
        rotation_mult=1.0,
        energy_turbulence=0.045,
        ray_intensity=0.22,
        ray_length=0.30,
        particle_activity=0.05,
        flash_rate=0.0,
        ripple_strength=0.0,
    ),
    "LISTENING": StateParams(
        glow_intensity=1.12,
        rotation_mult=1.15,
        energy_turbulence=0.07,
        ray_intensity=0.30,
        ray_length=0.36,
        particle_activity=0.18,
        flash_rate=0.4,
        ripple_strength=0.15,
    ),
    "THINKING": StateParams(
        glow_intensity=1.30,
        rotation_mult=1.6,
        energy_turbulence=0.12,
        ray_intensity=0.40,
        ray_length=0.42,
        particle_activity=0.45,
        flash_rate=3.0,
        ripple_strength=0.55,
    ),
    "SPEAKING": StateParams(
        glow_intensity=1.55,
        rotation_mult=1.35,
        energy_turbulence=0.22,
        ray_intensity=0.85,
        ray_length=0.70,
        particle_activity=1.0,
        flash_rate=1.2,
        ripple_strength=0.85,
    ),
}


@dataclass(frozen=True)
class Config:
    window: WindowConfig = field(default_factory=WindowConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    palette: Palette = field(default_factory=Palette)
    timings: Timings = field(default_factory=Timings)
    geometry: Geometry = field(default_factory=Geometry)
    particles: ParticleConfig = field(default_factory=ParticleConfig)
    post: PostConfig = field(default_factory=PostConfig)


CONFIG = Config()
