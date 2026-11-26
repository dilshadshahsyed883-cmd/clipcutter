"""Integer-millisecond strict duration partitioning without desktop-global settings."""
import math

def bounded_parts(duration: float, minimum: float, maximum: float):
    if not all(math.isfinite(x) for x in (duration, minimum, maximum)) or duration < 0 or not 0 < minimum <= maximum:
        raise ValueError("Invalid duration limits")
    total = round(duration * 1000)
    lo = math.ceil(minimum * 1000 - 1e-8)
    hi = math.floor(maximum * 1000 + 1e-8)
    if not 0 < lo <= hi:
        raise ValueError("No feasible millisecond range")
    count = total // lo
    if not count:
        return []
    # Fewest clips that keep the whole range, or maximize usable duration.
    n = min(count, math.ceil(total / hi))
    usable = min(total, n * hi)
    base, extra = divmod(usable, n)
    if base < lo:
        raise ValueError("No feasible partition")
    pos = 0
    parts = []
    for i in range(n):
        end = pos + base + (i < extra)
        parts.append((pos / 1000, end / 1000))
        pos = end
    return parts
