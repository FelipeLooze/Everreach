"""Integer C1 RPG parameterization, not an atmosphere solver or weather model."""
from heapq import heappop, heappush
from math import isqrt

from .geometry import Q, unit

# Sixteen fixed local hour angles. No platform libm in authoritative decisions.
HOUR_COS = (1000000, 923880, 707107, 382683, 0, -382683, -707107, -923880,
            -1000000, -923880, -707107, -382683, 0, 382683, 707107, 923880)


def sine_mdeg(angle):
    """Bhaskara-I rational approximation on 0..90 degrees (versioned)."""
    product = angle*(180_000-angle)
    return 4*product*Q//(40_500_000_000-product)


def declinations(config):
    tilt = sine_mdeg(config.axial_tilt_mdeg)
    return 0, tilt, 0, -tilt


def solar_forcing(direction, sin_declination):
    sin_lat = max(-Q, min(Q, direction[2]))
    cos_lat = isqrt(max(0, Q*Q-sin_lat*sin_lat))
    cos_decl = isqrt(max(0, Q*Q-sin_declination*sin_declination))
    return sum(max(0, (sin_lat*sin_declination + cos_lat*cos_decl*c//Q)//Q) for c in HOUR_COS)//16


def seasonal_temperature(direction, maritime, config):
    solar = tuple(solar_forcing(direction, d) for d in declinations(config))
    average = sum(solar)//4
    mixed = (average*(Q-config.poleward_heat_transport_ppm)+250_000*config.poleward_heat_transport_ppm)//Q
    annual = config.radiative_offset_centi_c+mixed*config.insolation_gain_centi_c//Q
    response = (config.land_seasonal_response_ppm*(Q-maritime)+config.ocean_seasonal_response_ppm*maritime)//Q
    temperatures = tuple(annual+(s-average)*config.insolation_gain_centi_c*response//(Q*Q) for s in solar)
    return temperatures, solar


def wind(direction, sin_declination, config):
    x, y, z = direction
    belt_z = z-sin_declination*config.itcz_shift_ppm//Q
    hadley, polar = sine_mdeg(config.hadley_edge_mdeg), sine_mdeg(config.polar_edge_mdeg)
    middle = hadley <= abs(belt_z) < polar
    zonal = 700_000 if middle else -700_000
    meridional = (1 if middle else -1)*max(-Q, min(Q, belt_z))*400_000//Q
    east, north = (-y, x, 0), (-z*x//Q, -z*y//Q, Q-z*z//Q)
    return tuple((e*zonal+n*meridional)*config.wind_scale_milli_m_s//(Q*Q) for e, n in zip(east, north))


def lapse(temperature, height_above_sea, config):
    return temperature-max(0, height_above_sea)*config.lapse_centi_c_per_km//1000


def pet_milli_mm_day(temperature, solar, config):
    return max(0, temperature+500)*config.pet_scale_milli_mm_per_day*(300_000+2*solar)//(2500*Q)


def condensation(direction, declination, rise_m, config):
    tropical = max(0, Q-2*abs(direction[2]-declination*config.itcz_shift_ppm//Q))
    return min(850_000, config.base_condensation_ppm + tropical*config.convective_condensation_ppm//Q
               + max(0, rise_m)*config.orographic_condensation_ppm_per_km//1000)


def ocean_distances(adjacent, lengths, marine):
    distance = [None]*len(adjacent)
    pending = []
    for i, ocean in enumerate(marine):
        if ocean:
            distance[i] = 0
            heappush(pending, (0, i))
    while pending:
        d, node = heappop(pending)
        if distance[node] != d:
            continue
        for other in adjacent[node]:
            candidate = d+lengths[tuple(sorted((node, other)))]
            if distance[other] is None or candidate < distance[other]:
                distance[other] = candidate
                heappush(pending, (candidate, other))
    return tuple(distance)


def transport(stencils, retention, rain_fraction, ocean_source, iterations, *, node_order=None):
    """Synchronous bounded upwind relaxation; order cannot alter this result."""
    count = len(stencils)
    order = tuple(range(count)) if node_order is None else tuple(node_order)
    if sorted(order) != list(range(count)):
        raise ValueError("Transport order must cover each vertex exactly once")
    previous = list(ocean_source)
    rainfall, delta = [0]*count, Q
    for _ in range(iterations):
        current = [0]*count
        for i in order:
            pairs = stencils[i]
            incoming = sum(previous[j]*w for j, w in pairs)//sum(w for _, w in pairs)
            available = ocean_source[i] if ocean_source[i] else incoming*retention[i]//Q
            rainfall[i] = available*rain_fraction[i]//Q
            current[i] = ocean_source[i] if ocean_source[i] else available*(Q-rain_fraction[i])//Q
        delta = max(abs(a-b) for a, b in zip(current, previous))
        previous = current
    return tuple(previous), tuple(rainfall), delta
