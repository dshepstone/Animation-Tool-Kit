"""Implicit Euler damped spring. Coordinates and time are Maya-independent."""
import math


class Spring:
    def __init__(self, position):
        self.position = tuple(position)
        self.velocity = (0.0, 0.0, 0.0)

    def step(self, target, dt, frequency, damping):
        if dt <= 0 or not math.isfinite(dt):
            raise ValueError("dt must be finite and positive")
        omega = 2 * math.pi * frequency
        k = omega * omega
        denominator = 1 + 2 * damping * omega * dt + k * dt * dt
        self.velocity = tuple((v + dt * k * (g - p)) / denominator
                              for p, v, g in zip(self.position, self.velocity, target))
        self.position = tuple(p + dt * v for p, v in zip(self.position, self.velocity))
        if not all(math.isfinite(v) for v in self.position + self.velocity):
            raise ValueError("Spring produced a non-finite result")
        return self.position
