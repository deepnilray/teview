"""Analytic point-mass trajectory; no numeric PDEs or collision dynamics."""

def projectile(inputs, *, seed):
    g = inputs['acceleration']
    t = inputs['duration']
    m = inputs['mass']
    y0 = inputs['initial_height']
    vy0 = inputs['initial_velocity']
    y = y0 + vy0*t - 0.5*g*t*t
    vy = vy0 - g*t
    return {'height':float(y),'speed':float(abs(vy)),
            'energy':float(m*g*y + 0.5*m*vy*vy)}
