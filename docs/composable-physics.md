# Composable physical scenes

**Version:** 0.4.0 alpha. This is a bounded component-first compiler, not a general multiphysics solver. Existing experiment protocols continue to work.

## How the compiler works

1. A scene declares component instances, reusable `[[definitions]]`, electrical connections and world settings.
2. The compiler validates physical properties, references, units and supported component kinds. Numeric values are in SI. Unit-tagged strings are dimension checked.
3. Law discovery builds interactions from component traits and spatial / connection relationships. A spring between an anchor and a sphere adds Hooke's law. Each sphere intersecting a fluid layer receives a buoyancy force. No experiment-specific template is involved.
4. The mechanical kernel integrates two-dimensional translation with RK4 and handles discrete contact with restitution. Springs and ropes are compliant. A constant electric field exerts a force on charged spheres.
5. The circuit solver uses modified nodal analysis for ideal DC batteries, resistors, switches and lamps. An attached lamp turns electrical dissipation into thermal power and a prescribed optical power fraction. The thermal state has lumped heat capacity and cooling.
6. `simulate` exports `scene.tev`, `model.json`, `report.json` and `measurements.csv`. `scene-verify` replays the saved source and compares its output.

## Example

```toml
schema = 1
title = "Unknown combination"

[world]
gravity = [0, "-9.81 m/s^2"]
electric_field = ["10 V/m", 0]
duration = "2 s"
dt = "0.002 s"

[[components]]
id = "workpiece"
kind = "sphere"
position = [0, "0.2 m"]
radius = "0.08 m"
mass = "0.5 kg"
charge = "0.01 C"

[[components]]
id = "bath"
kind = "fluid"
surface = "0.5 m"
bottom = "-1 m"
density = "1000 kg/m^3"
```

See the executable examples `electrothermal.tev` and `ball_water_spring.tev`. The first defines and connects electrical parts; the second freely combines spring tension, gravity, buoyancy, fluid drag and electrical force.

## Current component kinds

| Kind | Model |
| --- | --- |
| sphere | Translation, mass, charge, linear drag and collisions |
| anchor | Fixed mechanical endpoint |
| spring | Hooke axial force, rest length, damping |
| rope | Tension-only compliant axial spring, **not** exact rigid constraint |
| fluid | Infinite horizontal slab, exact spherical cap displaced volume, linear drag |
| floor | Horizontal collision plane and normal restitution |
| battery | Ideal DC voltage source |
| resistor | Constant resistance |
| switch | Ideal open / short circuit |
| lamp | Constant resistance, fixed optical conversion fraction, lumped temperature |

Each kind has a strict physical property schema. New named variants can be built through `[[definitions]]` with `name`, `base` and property overrides. A new differential equation or truly new physical domain cannot yet be defined in the language.

## Critical physical distinctions

A bulb in a static external field does **not** automatically light: a field is not necessarily an electrical power supply to the bulb. Electrical power and light are derived only if the DC network actually delivers current and voltage to the lamp.

The simulator does not support fluid flow, finite-width tanks, magnetostatics, electromagnetic induction, nonlinear semiconductors, full optics, mechanical rotation, 3D dynamics, friction, continuous impact detection or an arbitrary differential-algebraic system.

Fluids are idealized horizontal layers and may not overlap. Contacts are discrete and can tunnel at large steps. Highly stiff springs require smaller time steps. Light output is a scalar power value, not a rendered image or a radiation spectrum.

**A successful simulation is not independent scientific validation.** Reports deliberately use `simulated_not_validated`. The included tests cover selected analytical cases (free fall, charge acceleration, buoyancy, oscillation periods, collisions, circuits, heating) and failure paths.

## Commands

```bash
tev scene-check examples/scenes/electrothermal.tev
tev scene-explain examples/scenes/ball_water_spring.tev
tev simulate examples/scenes/electrothermal.tev --out runs/lamp
tev scene-verify runs/lamp
```

The long-term architecture should add typed physical ports, a symbolic equation IR, extensible constitutive laws, nonlinear DAE solving, and verified adapters to existing numerical solvers. Do not add hardcoded experiment scenarios as a substitute for general laws.
