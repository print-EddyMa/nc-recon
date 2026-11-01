"""Storm tracking and great-circle helpers on NeuralGCM's lon x lat Gaussian grid."""
import numpy as np

A_EARTH = 6.371e6


def gc_dist_km(lat1, lon1, lat2, lon2, xp=np):
    p1, p2 = xp.deg2rad(lat1), xp.deg2rad(lat2)
    c = xp.sin(p1) * xp.sin(p2) + xp.cos(p1) * xp.cos(p2) * xp.cos(xp.deg2rad(lon2 - lon1))
    return A_EARTH / 1e3 * xp.arccos(xp.clip(c, -1.0, 1.0))


def vorticity(u, v, lon, lat):
    """Relative vorticity of (u, v) [..., lon, lat] on the sphere (s^-1)."""
    lam, phi = np.deg2rad(lon), np.deg2rad(lat)
    dvdl = (np.roll(v, -1, axis=-2) - np.roll(v, 1, axis=-2)) / (2 * (lam[1] - lam[0]))
    return (dvdl - np.gradient(u * np.cos(phi), phi, axis=-1)) / (A_EARTH * np.cos(phi))


def track(u850, v850, lon, lat, first_guess, search_km=600):
    """Follow the (lightly smoothed) 850-hPa vorticity maximum. u850, v850: [time, lon, lat].
    At 2.8 deg the core is ~1 grid cell, so positions carry ~+/-100 km of grid noise."""
    zeta = vorticity(u850, v850, lon, lat)
    zs = sum(np.roll(np.roll(zeta, i, -2), j, -1) for i in (-1, 0, 1) for j in (-1, 0, 1)) / 9
    LON, LAT = np.meshgrid(lon, lat, indexing="ij")
    guess, out = first_guess, []
    for t in range(zs.shape[0]):
        f = np.where(gc_dist_km(guess[0], guess[1], LAT, LON) < search_km, zs[t], -np.inf)
        i, j = np.unravel_index(np.argmax(f), f.shape)
        ii = [(i + d) % len(lon) for d in (-1, 0, 1)]
        jj = [min(max(j + d, 0), len(lat) - 1) for d in (-1, 0, 1)]
        w = np.clip(zs[t][np.ix_(ii, jj)], 0, None)
        if w.sum() <= 0:
            w = np.ones_like(w)
        dlon = ((LON[np.ix_(ii, jj)] - LON[i, j] + 180) % 360) - 180
        clat = (w * LAT[np.ix_(ii, jj)]).sum() / w.sum()
        clon = LON[i, j] + (w * dlon).sum() / w.sum()
        guess = (float(clat), float(((clon + 180) % 360) - 180))
        out.append(dict(lat=round(guess[0], 3), lon=round(guess[1], 3), vort850=float(zs[t, i, j])))
    return out


def region_weight(lon, lat, center, radius_km):
    LON, LAT = np.meshgrid(lon, lat, indexing="ij")
    return np.exp(-(gc_dist_km(center[0], center[1], LAT, LON) / radius_km) ** 2)
