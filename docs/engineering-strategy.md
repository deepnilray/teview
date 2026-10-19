# TEVIEW — Engineering strategy and release gates

*Technical assessment based on the v0.5 physics kernel and scientific viewer, October 2026.*

## Product decision

TEVIEW should be a **text-first compiler and workbench for composable physical models**, not a universal simulator claimed to outperform every specialized engine. Its differentiator must be that physical interfaces, equations, constraints, and units determine valid interactions; a new *arrangement* must not require a new application-specific handler.

Commercial and open-source systems already excel at different pieces of this: Modelica and ModelingToolkit for equation-based acausal connections; FMI for model-exchange and co-simulation; Warp for accelerated spatial kernels. We should adopt established interfaces and reusable methods where possible instead of reproducing the entire numerical sciences ecosystem.

## Current state — gaps that threaten credibility

1. **No general equation intermediate representation.** In `teview_physics.py` the law-discovery table describes a rule, but concrete force/circuit/thermal implementations still contain handcoded per-kind paths. Adding a material law requires Python source changes, not merely registering a physical equation.
2. **No numerical accuracy guarantee.** Replay only proves deterministic re-execution, not correctness. The new `tev scene-converge` diagnoses final-observable time-step sensitivity (dt, dt/2, dt/4), but is not a substitute for independent analytical, manufactured-solution, or benchmark validation.
3. **Idealized and incomplete mechanics.** Only 2D translation; no torques, rotations, joints, rigid friction, continuous collision detection, 3D geometry, robust constraints, or accurate event localization. Discrete collisions may tunnel.
4. **Domain-limited coupling.** DC circuit solve is isolated from mechanical time stepping; optical absorption uses unshadowed point-source geometry; fluid is a stationary horizontal slab; electric field has no Maxwell evolution or induction. A physically plausible assembly can produce an incomplete answer.
5. **Text format does not admit user-defined constitutive equations.** TOML is a fine initial protocol container but lacks expression syntax, types, equations, inheritance semantics, and source-location diagnostics sufficient for a compiler platform.
6. **No edit-and-rerun visual workflow.** The scientific viewer is playback of saved results, not a live IDE. Coordinates are metric, but no visual action recompiles or reruns a scene.
7. **No engine adapter contract.** High-fidelity FEM, CFD, PIC, ray optics, particle transport and nonlinear DAE solvers require an integration layer. A single Python RK4 solver will not scale to all these classes.
8. **Unsandboxed plugin execution.** User-supplied Python commands have current-user privileges. Trust boundaries must be explicit and safer execution options provided before hosting online experiments.
9. **Unproven adoption.** Passing internal tests or publishing on GitHub is not market validation. There is no documented independent user study on real research workflows.

## Target architecture (interfaces over demo cases)

```text
.tev source / Python API / external model files
       |
   Syntax + type + dimension checking
       |
 Component graph (instances, material properties, typed ports, domains)
       |
 Physical equations + boundary conditions + event constraints
       |
 Typed mathematical IR (algebraic, ODE, DAE, PDE, discontinuities)
       |
 Model diagnostics (degrees of freedom, structural index, conservation)
       |
 Solver plan ---- adapters: native / Modelica-FMI / SciML / FEM / PIC
       |
 Time evolution + events + conserved-quantity / convergence monitors
       |
 Versioned scene+state+observables stream (SI units, provenance)
       |
 Scientific viewer + measurements + export + reproducibility gates
```

For connected components, introduce **potential/flow** variables: electrical voltage/current, thermal temperature/heat flow, mechanical displacement/force, fluid pressure/flow. Connections impose potential equality and flow conservation. Free-space electromagnetic forces and collision/contact are spatial interactions, not port connections; the compiler must distinguish them.

## Roadmap by stage, with acceptance gates

### P0: Trust before breadth (immediate)

- Expose numerical diagnostics: time-step refinement, energy/momentum/charge budgets where applicable; report initial-state collisions and singular configurations.
- Add solver-failure conditions for nonfinite states, under-resolved contact, circuit degeneracy, and ill-conditioned matrices. Reject rather than silently embellish.
- Build an independent benchmark corpus: ballistic motion, harmonic oscillator, two-body electrostatics, RLC and RC transients (once implemented), fluid hydrostatics, thermal equilibration.
- **Gate:** each model has analytic/reference tolerances, assumptions, and failure diagnostics. No physically incorrect demo passes as “validated.”

### P1: Real component architecture

- Register traits and interfaces separately from object names. Component definitions declare equations, units, states, params, and ports.
- Implement typed equation IR and structural checks for unknowns vs independent equations; detect underdetermined/overdetermined systems.
- Add acausal connectors, events, mechanical constraints and energy-accounting hooks.
- **Gate:** an external contributor builds a previously unseen compatible component and assembles it into three new scenes without touching the central compiler.

### P2: Compiler-to-solver interchange

- Add FMI 3.0 Model Exchange and Co-Simulation adapters with contract tests; native time stepping remains a lightweight backend.
- Implement partitioning, synchronization, event propagation, and explicit coupling tolerances; distinguish weak from strongly coupled models.
- **Gate:** a standard external solver and native TEVIEW produce benchmark-equivalent observables on a shared scene; divergences are diagnosed.

### P3: Browser scientific workbench

- Source editor with schema-based completions, unit annotations, inline errors; component inspector linked to source.
- Run/re-run via local service or safe remote worker; timeline, snapshots, reproducible captures, and comparison overlay.
- Scientific modes: metric rulers, object IDs, field probes with legends/units, adaptive sampling, uncertainty bars, convergence warnings and explicit schematic-vs-scale semantics.
- **Gate:** a first-time user changes component mass/charge and can reproduce, inspect, and export the new run in under 10 minutes without reading implementation code.

### P4: Domain plugins and performance

- Backends selected for problem class: robust rigid-body/contact, DAE, FEM PDEs, PIC and accelerator tracking, circuit transients, optics, stochastic/quantum domain adapters where physically appropriate.
- Profile representative workloads; add spatial acceleration (broad-phase BVH/hash grids), sparse Jacobians, parallel assembly, batching, GPU as a justified backend rather than a visual checkbox.
- **Gate:** measured scaling curves and comparison against the best available baseline, with error as well as speed reported.

## Visualization requirements

- Separate physical geometry from symbolic glyphs (e.g., a lamp symbol must never imply it occupies a measured area).
- Label coordinate frame, unit scale, interpolation, time sampling and any exaggeration; plotted force/field magnitudes require vector scales or a direction-only legend.
- Do not draw effects absent from computed observables (fluid waves, radiation wavefronts, induced currents, collision flashes).
- Make export reproducible: a frame must identify model/source hash, simulated time, solver, and observable channels.
- For complex scenes use spatial indexing, geometry culling, WebGL/WebGPU or a retained scene graph only when profiling justifies it.

## Security and reliability

- Prohibit arbitrary expression evaluation during parsing. Model extension execution must be explicitly trusted, versioned, and isolated before any multiuser server.
- Bound model size, wall-clock, memory, steps and output sizes; constrain uploads and exported artifact paths.
- Verify plugin and numerical-backend dependency versions and native binaries; version the IR and snapshots for backward compatibility.
- Separate `compiled`, `simulated`, `replayed`, `refinement_stable` and `experimentally_validated` statuses.

## Adoption testing, not hypothetical market victory

1. Recruit five domain researchers and five scientific Python developers who have existing experiments.
2. Measure setup time, model correctness, diagnostic discovery, time to changed result, and export/reproduction success against their existing workflows.
3. Do not declare superiority unless TEVIEW beats a particular incumbent on a defined workload and accuracy metric.
4. If users already have Modelica or SciML models, prioritize interoperability; do not make them rewrite their entire model for a new format.

## What not to do

- Do not add a new handcoded “bulb in field,” “three balls,” or “particle collision” scenario to claim emergent physics.
- Do not advertise a 2D RK4 kernel as CERN-grade detector simulation, quantum field theory, or full CFD.
- Do not optimize aesthetic effects at the expense of calibrated scientific quantities.
- Do not rewrite mature solvers unless a verified performance or functionality gap justifies the cost.

## Research references

- Modelica Language Specification: https://specification.modelica.org/
- ModelingToolkit acausal components: https://docs.sciml.ai/ModelingToolkit/stable/
- Functional Mock-up Interface 3.0: https://fmi-standard.org/docs/3.0.2/
- NVIDIA Warp: https://nvidia.github.io/warp/latest/

**Execution principle:** We do not need the most physics *names* in the component library; we need the most reliable and extensible way to derive valid equations from independently authored component models.