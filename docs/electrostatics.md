# Composable electrostatics (experimental)

TEVIEW v0.5 adds field interactions defined by component properties, not
by experiment names. The same law applies to previously unseen arrangements
of charged spheres, fixed sources and measurement probes.

## Example

```bash
tev scene-check examples/scenes/electrostatic_field.tev
tev scene-explain examples/scenes/electrostatic_field.tev
tev simulate examples/scenes/electrostatic_field.tev --out runs/electrostatic
tev scene-verify runs/electrostatic
```

Change either charge, add another charged sphere or relocate a probe: the
equations and forces update automatically. The output includes field vector
components (V/m) and electric potential (V) measured at every probe.

## Supported components and parameters

- `sphere`: moving 2D sphere with `charge` in coulombs, `mass`,
  `radius`, `position` and optional initial `velocity`.
- `fixed_charge`: stationary idealized charge at `position`, with `charge`
  and optional excluded radius. Not a mechanical collision obstacle.
- `field_probe`: non-invasive sensor with `position`. Reports `electric_field_x`,
  `electric_field_y`, and `potential`.
- `world.electric_field`: background uniform applied electric field.
- `world.relative_permittivity`: positive constant for an ideal homogeneous
  linear dielectric, default 1. This is not a material geometry solver.

## Equations and assumptions

In the plane of motion, each charged source contributes a three-dimensional
Coulomb electric field

```text
E(r) = [1/(4*pi*epsilon_0*epsilon_r)] * q * (r-r0)/|r-r0|^3
F = Q*E_total
```

Fields superpose with the externally declared uniform field. A moving
charged sphere reacts to every other charged sphere or fixed source.
A probe measures that total field without exerting a force.

This is a *3D Coulomb model sampled in a 2D simulation*, not the mathematical
electrostatics of a truly two-dimensional universe. Charged spheres use
their exterior point-charge field. Interior or coincident field evaluations
are rejected. A fixed charge source has no mechanical collision handling.

The current solver does not model conduction through materials, electric
induction, magnetic effects, nonlinear dielectrics, screening, surfaces,
boundaries, polarization, electromagnetic radiation, or Maxwell PDEs.
Strong close-range forces can require smaller numerical time steps. Results
are computational predictions, **not independently validated measurements**.

## Verification

The regression suite covers the inverse-square relation, superposition,
polarity, permittivity scaling, energy and momentum conservation,
neutral-body invariance, singularity handling, and work limits.

```bash
python -m unittest discover -s tests -v
```

A replay check confirms saved computations reproduce in the current
environment; it does not prove the underlying scientific approximation.
