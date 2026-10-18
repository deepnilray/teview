"""TEVIEW composable physical scene kernel (SI units, 2D translation + lumped circuits).

This is an intentionally bounded model. Shared laws interact with component traits,
not named experiment templates. Unsupported domains are rejected, not simulated.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import tomllib
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


class PhysicsError(ValueError):
    """Invalid physical model or unsupported configuration."""


# factor relative to SI, and semantic dimensional category
UNITS = {
    'm': (1., 'length'), 'cm': (.01, 'length'), 'mm': (.001, 'length'),
    'km': (1000., 'length'), 'kg': (1., 'mass'), 'g': (.001, 'mass'),
    's': (1., 'time'), 'ms': (.001, 'time'),
    'm/s': (1., 'velocity'), 'm/s^2': (1., 'acceleration'),
    'kg/m^3': (1., 'density'), 'N/m': (1., 'stiffness'),
    'N*s/m': (1., 'damping'), 'kg/s': (1., 'damping'),
    'C': (1., 'charge'), 'V/m': (1., 'electric_field'),
    'V': (1., 'voltage'), 'ohm': (1., 'resistance'),
    'J/K': (1., 'heat_capacity'), 'W/K': (1., 'conductance'),
    'K': (1., 'temperature'), 'W': (1., 'power'),
}
NUMERIC = re.compile(r'^\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*([^\s].*?)?\s*$')


def si(value, dimension, field):
    if isinstance(value, bool):
        raise PhysicsError(f'{field}: expected a {dimension} number, not a boolean')
    if isinstance(value, (float, int)):
        result = float(value)
    elif isinstance(value, str):
        m = NUMERIC.fullmatch(value)
        if not m or not m.group(2):
            raise PhysicsError(f'{field}: expected a number with units, such as "2 m"')
        unit = m.group(2).strip()
        if unit not in UNITS or UNITS[unit][1] != dimension:
            raise PhysicsError(f'{field}: unit "{unit}" is incompatible with {dimension}')
        result = float(m.group(1)) * UNITS[unit][0]
    else:
        raise PhysicsError(f'{field}: expected numeric {dimension}')
    if not math.isfinite(result):
        raise PhysicsError(f'{field}: value must be finite')
    return result


def scalar(value, field):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise PhysicsError(f'{field}: expected a finite dimensionless number')
    return float(value)


def vector(value, dimension, field):
    if not isinstance(value, list) or len(value) != 2:
        raise PhysicsError(f'{field}: expected a 2-element vector')
    return tuple(si(v, dimension, field) for v in value)


def positive(x, field, allow_zero=False):
    if x < 0 if allow_zero else x <= 0:
        raise PhysicsError(f'{field}: must be {"nonnegative" if allow_zero else "positive"}')
    return x


# Schema: field -> (kind, default, required). Non-specific experiments never
# appear here. Add a component trait or a law, not a demonstration-specific case.
FIELDS = {
    'sphere': {
        'position': ('vec:length', None, True), 'velocity': ('vec:velocity', [0, 0], False),
        'radius': ('length', None, True), 'mass': ('mass', None, True),
        'charge': ('charge', 0, False), 'drag': ('damping', 0, False),
        'restitution': ('fraction', 1, False),
    },
    'anchor': {'position': ('vec:length', None, True)},
    'fluid': {
        'surface': ('length', None, True), 'bottom': ('length', -1e6, False),
        'density': ('density', None, True), 'drag': ('damping', 0, False),
    },
    'floor': {'height': ('length', None, True), 'restitution': ('fraction', 1, False)},
    'spring': {
        'a': ('ref', None, True), 'b': ('ref', None, True),
        'stiffness': ('stiffness', None, True), 'rest_length': ('length', None, True),
        'damping': ('damping', 0, False),
    },
    'rope': {
        'a': ('ref', None, True), 'b': ('ref', None, True),
        'stiffness': ('stiffness', None, True), 'length': ('length', None, True),
        'damping': ('damping', 0, False),
    },
    'battery': {'voltage': ('voltage', None, True)},
    'resistor': {'resistance': ('resistance', None, True)},
    'lamp': {
        'resistance': ('resistance', None, True), 'light_fraction': ('fraction', .08, False),
        'heat_capacity': ('heat_capacity', 10, False), 'cooling': ('conductance', .5, False),
        'temperature': ('temperature', 293.15, False),
    },
    'switch': {'closed': ('bool', False, False)},
}
PORTS = {'battery': {'positive', 'negative'}, 'resistor': {'a', 'b'},
         'lamp': {'a', 'b'}, 'switch': {'a', 'b'}}
ELECTRICAL = frozenset(PORTS)
KINDS = frozenset(FIELDS)
LAW_EQUATIONS = {
    'gravity': 'F = m*g',
    'electric_force': 'F = q*E',
    'buoyancy_and_drag': 'F_buoyancy = -rho*V_submerged*g; F_drag = -c*(V_submerged/V_sphere)*v',
    'hooke': 'F_tension = k*(length-rest_length) + damping*d(length)/dt',
    'tension_only': 'F_tension = max(0, k*(length-rest_length)+damping*d(length)/dt) when stretched',
    'sphere_contact': 'Normal impulse: J = -(1+e)*relative_normal_speed/(1/m1+1/m2)',
    'floor_contact': 'Normal velocity reflects with coefficient of restitution',
    'ideal_dc_network': 'Kirchhoff node balance + Ohm law I = Delta(V)/R',
    'joule_heating_and_emission': 'P = I^2*R; P_light = efficiency*P; C*dT/dt = (1-efficiency)*P - h*(T-Tambient)',
}



def _read_field(raw, dim, field):
    if dim.startswith('vec:'):
        return vector(raw, dim[4:], field)
    if dim == 'fraction':
        n = scalar(raw, field)
        if not 0 <= n <= 1:
            raise PhysicsError(f'{field}: must be between 0 and 1')
        return n
    if dim == 'bool':
        if not isinstance(raw, bool):
            raise PhysicsError(f'{field}: expected true/false')
        return raw
    if dim == 'ref':
        if not isinstance(raw, str) or not raw or '.' in raw:
            raise PhysicsError(f'{field}: expected an object identifier')
        return raw
    return si(raw, dim, field)


def load_scene(path):
    source = Path(path)
    with source.open('rb') as f:
        raw = tomllib.load(f)
    return compile_scene(raw, source.read_bytes())


@dataclass
class Scene:
    components: dict
    bodies: list
    gravity: tuple
    electric_field: tuple
    ambient_temperature: float
    duration: float
    dt: float
    steps: int
    connections: list
    interactions: list
    source_hash: str
    title: str


def compile_scene(raw, content=b''):
    if not isinstance(raw, dict) or set(raw) - {'schema', 'title', 'world', 'definitions', 'components', 'connections'}:
        raise PhysicsError('Unknown top-level keys in scene')
    if raw.get('schema') != 1:
        raise PhysicsError('Scene requires schema = 1')
    world = raw.get('world', {})
    if not isinstance(world, dict) or set(world) - {'gravity', 'electric_field', 'duration', 'dt', 'ambient_temperature'}:
        raise PhysicsError('world: unknown settings')
    gravity = vector(world.get('gravity', [0, -9.81]), 'acceleration', 'world.gravity')
    efield = vector(world.get('electric_field', [0, 0]), 'electric_field', 'world.electric_field')
    ambient = positive(si(world.get('ambient_temperature', 293.15),
                          'temperature', 'world.ambient_temperature'), 'ambient_temperature')
    duration = positive(si(world.get('duration', 1), 'time', 'world.duration'), 'duration')
    dt = positive(si(world.get('dt', .005), 'time', 'world.dt'), 'dt')
    steps = math.ceil(duration / dt)
    if steps > 100000:
        raise PhysicsError('Too many simulation steps (maximum 100000)')
    if not isinstance(raw.get('definitions', []), list) or not isinstance(raw.get('components', []), list) or not isinstance(raw.get('connections', []), list):
        raise PhysicsError('definitions, components and connections must be arrays')
    if len(raw.get('components', [])) > 300 or len(raw.get('connections', [])) > 1000:
        raise PhysicsError('Scene exceeds component or connection safety limits')
    defs = {}
    for d in raw.get('definitions', []):
        if not isinstance(d, dict) or not isinstance(d.get('name'), str) or not d['name'].isidentifier():
            raise PhysicsError('A reusable definition needs a valid name')
        name = d['name']
        if name in defs or name in KINDS:
            raise PhysicsError(f'Duplicate or reserved definition: {name}')
        base = d.get('base')
        if base not in KINDS:
            raise PhysicsError(f'Unknown base component: {base}')
        defs[name] = {k: v for k, v in d.items() if k != 'name'}
    components = {}
    for raw_part in raw.get('components', []):
        if not isinstance(raw_part, dict) or not isinstance(raw_part.get('id'), str) or not raw_part['id'].isidentifier():
            raise PhysicsError('Every component needs an identifier')
        name = raw_part['id']
        if name in components:
            raise PhysicsError(f'Duplicate component {name}')
        kind = raw_part.get('kind')
        if kind in defs:
            cfg = {**defs[kind], **raw_part}
            kind = cfg.pop('base')
            cfg['kind'] = kind
        else:
            cfg = raw_part.copy()
        if kind not in KINDS:
            raise PhysicsError(f'{name}: unknown component kind {kind}')
        invalid = set(cfg) - (set(FIELDS[kind]) | {'id', 'kind'})
        if invalid:
            raise PhysicsError(f'{name}: unknown properties: {", ".join(sorted(invalid))}')
        part = {'id': name, 'kind': kind}
        for key, (dim, default, req) in FIELDS[kind].items():
            if req and key not in cfg:
                raise PhysicsError(f'{name}: missing required property {key}')
            part[key] = _read_field(cfg.get(key, default), dim, f'{name}.{key}')
        if kind == 'sphere':
            positive(part['radius'], f'{name}.radius')
            positive(part['mass'], f'{name}.mass')
        elif kind == 'fluid':
            positive(part['density'], f'{name}.density')
            if part['surface'] <= part['bottom']:
                raise PhysicsError(f'{name}: fluid surface must exceed bottom')
        elif kind in ('spring', 'rope'):
            positive(part['stiffness'], f'{name}.stiffness')
            positive(part['rest_length'] if kind == 'spring' else part['length'], f'{name}.length', True)
        elif kind in ('resistor', 'lamp'):
            positive(part['resistance'], f'{name}.resistance')
        elif kind == 'lamp':
            pass
        if kind == 'lamp':
            positive(part['heat_capacity'], f'{name}.heat_capacity')
            positive(part['temperature'], f'{name}.temperature')
        components[name] = part
    if not components:
        raise PhysicsError('A scene requires components')
    fluids = [p for p in components.values() if p['kind'] == 'fluid']
    for i, left in enumerate(fluids):
        for right in fluids[i+1:]:
            if max(left['bottom'], right['bottom']) < min(left['surface'], right['surface']):
                raise PhysicsError(f'{left["id"]} overlaps {right["id"]}; overlapping fluid volumes are unsupported')
    floors=[p for p in components.values() if p['kind']=='floor']
    for b in (p for p in components.values() if p['kind']=='sphere'):
        for f in floors:
            if b['position'][1]-b['radius'] < f['height']-1e-9:
                raise PhysicsError(f'{b["id"]} starts below floor {f["id"]}')
    for p in components.values():
        if p['kind'] in ('spring', 'rope'):
            for key in ('a', 'b'):
                ref = p[key]
                if ref not in components or components[ref]['kind'] not in ('sphere', 'anchor'):
                    raise PhysicsError(f'{p["id"]}.{key}: must reference a sphere or anchor')
            if p['a'] == p['b']:
                raise PhysicsError(f'{p["id"]}: both endpoints refer to the same object')
    connections = []
    for conn in raw.get('connections', []):
        if not isinstance(conn, dict) or set(conn) != {'a', 'b'}:
            raise PhysicsError('Each connection must have a and b terminals only')
        endpoints = []
        for terminal in (conn['a'], conn['b']):
            if not isinstance(terminal, str) or terminal.count('.') != 1:
                raise PhysicsError('Electrical terminals use component.port notation')
            cid, port = terminal.split('.')
            if cid not in components or port not in PORTS.get(components[cid]['kind'], ()):
                raise PhysicsError(f'Unknown electrical terminal {terminal}')
            endpoints.append(terminal)
        if endpoints[0] == endpoints[1]:
            raise PhysicsError('Cannot connect a terminal to itself')
        connections.append(endpoints)
    interactions = []
    spheres = [p for p in components.values() if p['kind'] == 'sphere']
    for b in spheres:
        if gravity != (0., 0.):
            interactions.append({'law': 'gravity', 'objects': [b['id']]})
        if b['charge'] and efield != (0., 0.):
            interactions.append({'law': 'electric_force', 'objects': [b['id']]})
        for f in components.values():
            if f['kind'] == 'fluid':
                interactions.append({'law': 'buoyancy_and_drag', 'objects': [b['id'], f['id']]})
            elif f['kind'] == 'floor':
                interactions.append({'law': 'floor_contact', 'objects': [b['id'], f['id']]})
    for p in components.values():
        if p['kind'] in ELECTRICAL:
            interactions.append({'law': 'ideal_dc_network', 'objects': [p['id']]})
        if p['kind'] in ('spring', 'rope'):
            interactions.append({'law': 'hooke' if p['kind'] == 'spring' else 'tension_only',
                                 'objects': [p['a'], p['id'], p['b']]})
        if p['kind'] == 'lamp':
            interactions.append({'law': 'joule_heating_and_emission', 'objects': [p['id']]})
    for i, a in enumerate(spheres):
        for b in spheres[i+1:]:
            interactions.append({'law': 'sphere_contact', 'objects': [a['id'], b['id']]})
    for interaction in interactions:
        interaction['equation'] = LAW_EQUATIONS[interaction['law']]
    return Scene(components, [p['id'] for p in spheres], gravity, efield, ambient, duration,
                 dt, steps, connections, interactions,
                 hashlib.sha256(content if content else repr(raw).encode()).hexdigest(),
                 str(raw.get('title', 'Untitled scene')))


def _add(a, b):
    return (a[0]+b[0], a[1]+b[1])


def _sub(a, b):
    return (a[0]-b[0], a[1]-b[1])


def _mul(a, f):
    return (a[0]*f, a[1]*f)


def _dot(a, b):
    return a[0]*b[0]+a[1]*b[1]


def _sphere_below(r, h):
    h = max(0., min(2*r, h))
    return math.pi*h*h*(r-h/3.)


def displaced_volume(r, center_y, bottom, surface):
    """Exact sphere volume within a horizontally unbounded fluid layer."""
    return (_sphere_below(r, surface-center_y+r) -
            _sphere_below(r, bottom-center_y+r))


def _mechanical_force(scene, state):
    c = scene.components
    forces = {name: _mul(scene.gravity, c[name]['mass']) for name in scene.bodies}
    for name in scene.bodies:
        p = c[name]
        x, y, vx, vy = state[name]
        f = forces[name]
        f = _add(f, _mul(scene.electric_field, p['charge']))
        f = _sub(f, _mul((vx, vy), p['drag']))
        for other in c.values():
            if other['kind'] != 'fluid':
                continue
            vol = displaced_volume(p['radius'], y, other['bottom'], other['surface'])
            f = _sub(f, _mul(scene.gravity, other['density']*vol))
            vratio = vol/(4./3.*math.pi*p['radius']**3)
            f = _sub(f, _mul((vx, vy), other['drag']*vratio))
        forces[name] = f
    for link in c.values():
        if link['kind'] not in ('spring', 'rope'):
            continue
        def endpoint(ref):
            if ref in state:
                return (state[ref][0:2], state[ref][2:4])
            return (c[ref]['position'], (0., 0.))
        (a, va), (b, vb) = endpoint(link['a']), endpoint(link['b'])
        d = _sub(b, a)
        length = math.hypot(*d)
        if length <= 1e-14:
            continue
        direction = _mul(d, 1./length)
        stretch = length - (link['rest_length'] if link['kind']=='spring' else link['length'])
        speed = _dot(_sub(vb, va), direction)
        tension = link['stiffness']*stretch + link['damping']*speed
        if link['kind']=='rope':
            tension = max(0., tension) if stretch > 0 else 0.
        force = _mul(direction, tension)
        if link['a'] in forces:
            forces[link['a']] = _add(forces[link['a']], force)
        if link['b'] in forces:
            forces[link['b']] = _sub(forces[link['b']], force)
    return forces


def _rk4(scene, state, dt):
    def rhs(s):
        f = _mechanical_force(scene, s)
        return {name:(s[name][2],s[name][3], f[name][0]/scene.components[name]['mass'],
                      f[name][1]/scene.components[name]['mass']) for name in scene.bodies}
    def advance(s,k,h):
        return {name: tuple(s[name][j]+h*k[name][j] for j in range(4)) for name in s}
    if not state:
        return {}
    k1 = rhs(state)
    k2 = rhs(advance(state,k1,dt/2))
    k3 = rhs(advance(state,k2,dt/2))
    k4 = rhs(advance(state,k3,dt))
    return {name: tuple(state[name][j]+dt*(k1[name][j]+2*k2[name][j]+2*k3[name][j]+k4[name][j])/6
                        for j in range(4)) for name in state}


def _resolve_collisions(scene, state):
    """Discrete 2D frictionless impact response; not continuous collision detection."""
    c = scene.components
    s = {k:list(v) for k,v in state.items()}
    for name in scene.bodies:
        b = c[name]
        for floor in c.values():
            if floor['kind'] == 'floor' and s[name][1]-b['radius'] < floor['height']:
                s[name][1] = floor['height']+b['radius']
                if s[name][3] < 0:
                    s[name][3] = -s[name][3]*min(b['restitution'], floor['restitution'])
    for i,a in enumerate(scene.bodies):
        for b in scene.bodies[i+1:]:
            pa, pb = c[a],c[b]
            delta = (s[b][0]-s[a][0], s[b][1]-s[a][1])
            ds = math.hypot(*delta)
            min_dist = pa['radius']+pb['radius']
            if ds >= min_dist:
                continue
            if ds == 0:
                raise PhysicsError(f'{a} and {b}: centers coincide; contact normal undefined')
            n = _mul(delta, 1/ds)
            inva, invb = 1/pa['mass'],1/pb['mass']
            penetration = min_dist-ds
            s[a][0] -= n[0]*penetration*inva/(inva+invb)
            s[a][1] -= n[1]*penetration*inva/(inva+invb)
            s[b][0] += n[0]*penetration*invb/(inva+invb)
            s[b][1] += n[1]*penetration*invb/(inva+invb)
            speed = (s[b][2]-s[a][2])*n[0]+(s[b][3]-s[a][3])*n[1]
            if speed < 0:
                impulse = -(1+min(pa['restitution'],pb['restitution']))*speed/(inva+invb)
                s[a][2] -= impulse*inva*n[0]
                s[a][3] -= impulse*inva*n[1]
                s[b][2] += impulse*invb*n[0]
                s[b][3] += impulse*invb*n[1]
    return {k:tuple(v) for k,v in s.items()}


class _DSU:
    def __init__(self):
        self.parent = {}
    def find(self, x):
        self.parent.setdefault(x,x)
        if self.parent[x]!=x:
            self.parent[x]=self.find(self.parent[x])
        return self.parent[x]
    def union(self,a,b):
        self.parent[self.find(a)] = self.find(b)


def _linear_solve(A, b):
    n=len(b)
    a=[row[:]+[b[i]] for i,row in enumerate(A)]
    for i in range(n):
        p=max(range(i,n),key=lambda j:abs(a[j][i]))
        if abs(a[p][i]) < 1e-12:
            raise PhysicsError('Circuit has a singular or inconsistent topology')
        a[i],a[p]=a[p],a[i]
        scale=a[i][i]
        for k in range(i,n+1):
            a[i][k]/=scale
        for j in range(n):
            if j==i: continue
            q=a[j][i]
            for k in range(i,n+1):
                a[j][k]-=q*a[i][k]
    return [row[n] for row in a]


def solve_circuit(scene):
    """Ideal DC nodal network using MNA; lamps are resistive thermal/optical loads."""
    c = scene.components
    dsu = _DSU()
    for comp in c.values():
        if comp['kind'] in ELECTRICAL:
            for port in PORTS[comp['kind']]:
                dsu.find(f"{comp['id']}.{port}")
    for a,b in scene.connections:
        dsu.union(a,b)
    for comp in c.values():
        if comp['kind']=='switch' and comp['closed']:
            dsu.union(f"{comp['id']}.a",f"{comp['id']}.b")
    resistive, sources = [], []
    for p in c.values():
        name, kind = p['id'],p['kind']
        if kind in ('resistor','lamp'):
            a,b=dsu.find(name+'.a'),dsu.find(name+'.b')
            resistive.append((name,a,b,p['resistance']))
        elif kind=='battery':
            a,b=dsu.find(name+'.positive'),dsu.find(name+'.negative')
            if a==b:
                raise PhysicsError(f'{name}: ideal voltage source is short-circuited')
            sources.append((name,a,b,p['voltage']))
    edges = [(a,b) for _,a,b,_ in resistive + sources if a!=b]
    adj=defaultdict(set)
    for a,b in edges:
        adj[a].add(b);adj[b].add(a)
    nodes=set(dsu.find(x) for x in dsu.parent)
    components=[]
    while nodes:
        root=min(nodes)
        stack=[root]; group=set()
        while stack:
            u=stack.pop()
            if u in group: continue
            group.add(u);stack.extend(adj[u]-group)
        nodes-=group
        components.append(group)
    voltages={}
    for group in components:
        vsrc=[e for e in sources if e[1] in group]
        rs=[e for e in resistive if e[1] in group]
        ground = sorted(group)[0]
        variable = {n:i for i,n in enumerate(sorted(group - {ground}))}
        n=len(variable)+len(vsrc)
        if not n:
            voltages[ground]=0.
            continue
        matrix=[[0.]*n for _ in range(n)]
        rhs=[0.]*n
        def stamp(n1,n2,g):
            if n1 in variable: matrix[variable[n1]][variable[n1]]+=g
            if n2 in variable: matrix[variable[n2]][variable[n2]]+=g
            if n1 in variable and n2 in variable:
                matrix[variable[n1]][variable[n2]]-=g
                matrix[variable[n2]][variable[n1]]-=g
        for _,a,b,R in rs:
            stamp(a,b,1./R)
        for j,(_,a,b,V) in enumerate(vsrc):
            idx=len(variable)+j
            rhs[idx]=V
            for node,sign in ((a,1),(b,-1)):
                if node in variable:
                    ix=variable[node]
                    matrix[ix][idx]+=sign
                    matrix[idx][ix]+=sign
        solution=_linear_solve(matrix,rhs)
        voltages.update({name:solution[i] for name,i in variable.items()})
        voltages[ground]=0.
    readings={}
    for name,a,b,R in resistive:
        v=voltages[a]-voltages[b]
        current=v/R
        output={'voltage':v,'current':current,'power':v*current}
        if c[name]['kind']=='lamp':
            output['light_power']=c[name]['light_fraction']*output['power']
            output['heat_power']=(1-c[name]['light_fraction'])*output['power']
        readings[name]=output
    for name,a,b,V in sources:
        readings[name]={'voltage':V}
    return readings


def _snapshot(scene, state, temperature, electric, time):
    result={'time':round(time,12)}
    for name in scene.bodies:
        x,y,vx,vy=state[name]
        result.update({f'{name}.x':x,f'{name}.y':y,f'{name}.vx':vx,f'{name}.vy':vy})
    for name,ev in electric.items():
        for k,v in ev.items():
            result[f'{name}.{k}']=v
    for name,temp in temperature.items():
        result[f'{name}.temperature']=temp
    return result


def simulate(scene, output=None):
    """Simulate independent DC circuit + electrothermal load + 2D mechanical laws."""
    state={name:(*scene.components[name]['position'],*scene.components[name]['velocity'])
           for name in scene.bodies}
    temperatures={p['id']:p['temperature'] for p in scene.components.values() if p['kind']=='lamp'}
    circuit=solve_circuit(scene)
    # Mechanical links: explicit numerics require resolution of the fastest timescale.
    for comp in scene.components.values():
        if comp['kind'] not in ('spring','rope'):continue
        masses=[scene.components[x]['mass'] for x in (comp['a'],comp['b']) if x in scene.bodies]
        if masses and scene.dt>0.15*math.sqrt(min(masses)/comp['stiffness']):
            raise PhysicsError(f'{comp["id"]}: dt too large for spring/rope stiffness; decrease world.dt')
    max_rows=1001
    stride=max(1,math.ceil(scene.steps/(max_rows-1)))
    rows=[_snapshot(scene,state,temperatures,circuit,0.)]
    t=0.
    for i in range(scene.steps):
        h=min(scene.dt, scene.duration-t)
        state=_resolve_collisions(scene,_rk4(scene,state,h))
        for name,temp in temperatures.items():
            lamp=scene.components[name]
            power=circuit[name]['heat_power']
            thermal=lamp['cooling']
            ambient=scene.ambient_temperature
            if thermal:
                decay=math.exp(-thermal*h/lamp['heat_capacity'])
                temperatures[name]=ambient+(temp-ambient)*decay+power/thermal*(1-decay)
            else:
                temperatures[name]=temp+h*power/lamp['heat_capacity']
        t=min(scene.duration,t+h)
        if (i+1)%stride==0 or i==scene.steps-1:
            rows.append(_snapshot(scene,state,temperatures,circuit,t))
    report={'title':scene.title,'source_sha256':scene.source_hash,'status':'simulated_not_validated',
            'model':'2D translation with RK4, discrete contact, ideal DC MNA, lumped electrothermal light fraction',
            'limitations':['No fluid flow, full Maxwell solver, induction, rigid rotation, or continuous collision detection',
                           'Ropes are compliant tension-only elements; lamp resistance and efficiency are constant',
                           'Electric fields exert forces on charges but do not automatically energize circuit terminals',
                           'Thermal radiation and optical transport are not modeled; light_power is a component output',
                           'SI values are used internally; numeric inputs are treated as SI'],
            'interactions':scene.interactions,'duration_s':scene.duration,'steps':scene.steps,
            'initial':rows[0],'final':rows[-1],'samples':len(rows)}
    if output is not None:
        path=Path(output)
        path.mkdir(parents=True,exist_ok=True)
        (path/'report.json').write_text(json.dumps(report,indent=2,sort_keys=True,allow_nan=False)+'\n',encoding='utf-8')
        (path/'model.json').write_text(json.dumps({'components':scene.components,'connections':scene.connections,
                                                    'interactions':scene.interactions,
                                                    'world':{'gravity':scene.gravity,
                                                    'electric_field':scene.electric_field,
                                                    'ambient_temperature':scene.ambient_temperature}},indent=2,sort_keys=True)+'\n',encoding='utf-8')
        with (path/'measurements.csv').open('w',newline='',encoding='utf-8') as handle:
            writer=csv.DictWriter(handle,fieldnames=rows[0].keys());writer.writeheader();writer.writerows(rows)
    return report,rows


def verify_scene(folder):
    """Replay a saved source snapshot and reject changed outputs or input bytes."""
    import tempfile
    folder=Path(folder)
    source=folder/'scene.tev'
    if not source.is_file():
        raise PhysicsError('Missing captured scene.tev source snapshot')
    model=load_scene(source)
    existing=json.loads((folder/'report.json').read_text(encoding='utf-8'))
    if model.source_hash != existing.get('source_sha256'):
        raise PhysicsError('Scene source hash mismatch')
    with tempfile.TemporaryDirectory() as tmp:
        report,_=simulate(model,tmp)
        for name in ('report.json','model.json','measurements.csv'):
            if (folder/name).read_bytes() != (Path(tmp)/name).read_bytes():
                raise PhysicsError(f'Replay mismatch or tampered output: {name}')
    return {'status':'replayed','source_sha256':model.source_hash,
            'interactions':len(model.interactions)}