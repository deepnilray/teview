#!/usr/bin/env python3
"""TEVIEW Evidence Core: executable, inspectable experimental protocols.

Python 3.11+, standard-library only. Intentionally NO untrusted-code sandbox.
"""
from __future__ import annotations

import argparse
import copy
import csv
from datetime import datetime, timezone
import hashlib
import types
import json
import math
import os
from pathlib import Path
import platform
import random
import re
import shutil
import statistics
import sys
import tempfile
import tomllib
import traceback

VERSION = '0.5.0-alpha'
MAX_JSON_BYTES = 5 * 1024 * 1024
IDENT = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')
REF = re.compile(r'^\$\{(parameters|arm|run|datasets|steps)\.([A-Za-z_][A-Za-z0-9_]*)(?:\.([A-Za-z_][A-Za-z0-9_]*))?\}$')

class ExperimentError(Exception):
    pass

def require(ok, msg):
    if not ok:
        raise ExperimentError(msg)

def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), allow_nan=False, ensure_ascii=False)

def digest(data):
    if not isinstance(data, bytes):
        data = canonical(data).encode('utf8')
    return hashlib.sha256(data).hexdigest()

def filehash(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):
            h.update(chunk)
    return h.hexdigest()

def relative_file(root, raw):
    require(isinstance(raw,str) and raw and not Path(raw).is_absolute(),f'file must be a relative path: {raw!r}')
    p=(root/raw).resolve()
    require(p.is_relative_to(root.resolve()), f'file escapes experiment folder: {raw}')
    require(p.is_file(), f'missing declared file: {raw}')
    return p

def strict_keys(obj, legal, where):
    require(isinstance(obj,dict), f'{where} must be a table')
    bad=set(obj)-set(legal)
    require(not bad, f'{where} contains unsupported keys: {sorted(bad)}')

def safe_name(s, where):
    require(isinstance(s,str) and bool(IDENT.fullmatch(s)), f'{where} must be a simple identifier')
    require(not s.startswith('__'), f'{where} cannot start with __')
    return s

def json_safe(obj, where='value'):
    try:
        enc=canonical(obj).encode('utf8')
    except (TypeError,ValueError) as ex:
        raise ExperimentError(f'{where} must be finite JSON-compatible data: {ex}') from ex
    require(len(enc)<=MAX_JSON_BYTES,f'{where} exceeds {MAX_JSON_BYTES} bytes')
    return obj

def check_type(v, t, where):
    types={'number':lambda x:type(x) in (float,int) and math.isfinite(x),
           'integer':lambda x:type(x) is int,
           'string':lambda x:type(x) is str,
           'boolean':lambda x:type(x) is bool,
           'array':lambda x:type(x) is list,
           'object':lambda x:type(x) is dict}
    require(t in types, f'{where}: unknown output type {t!r}')
    require(types[t](v), f'{where}: expected {t}, got {type(v).__name__}')

def plugin_source(uses):
    if uses.startswith('builtin:'):
        return None
    if uses.startswith('python:'):
        parts=uses.split(':')
        require(len(parts)==3, "python plugin format: python:relative_file.py:function")
        safe_name(parts[2],'Python function name')
        require(parts[1].endswith('.py'),'Python plugin must reference .py file')
        return parts[1]
    raise ExperimentError(f'unsupported operator {uses!r}')

def references(val):
    if isinstance(val,str):
        if val.startswith('${') or val.endswith('}'):
            m=REF.fullmatch(val)
            require(m is not None,f'invalid reference {val!r}; entire string must be a reference')
            return [m.groups()]
        return []
    if isinstance(val,list):
        return [r for v in val for r in references(v)]
    if isinstance(val,dict):
        return [r for v in val.values() for r in references(v)]
    return []

def load_spec(path):
    path=Path(path).resolve(); root=path.parent
    require(path.suffix=='.tev',f'expected .tev file: {path}')
    try:
        spec=tomllib.loads(path.read_text(encoding='utf8'))
    except (tomllib.TOMLDecodeError, UnicodeError) as ex:
        raise ExperimentError(f'cannot parse {path}: {ex}') from ex
    strict_keys(spec,{'schema','title','description','seed','replicates','paired','parameters','arms','datasets','steps','metrics','claims','guards'},'experiment')
    require(spec.get('schema')==1, 'schema must be 1')
    require(isinstance(spec.get('title'),str) and spec['title'].strip(),'title must be nonempty')
    require(isinstance(spec.get('seed',0),int) and type(spec.get('seed',0)) is int and spec.get('seed',0)>=0,'seed must be a nonnegative integer')
    reps=spec.get('replicates',1)
    require(type(reps) is int and 1<=reps<=10000,'replicates must be between 1 and 10000')
    require(type(spec.get('paired',False)) is bool,'paired must be boolean')
    params=spec.get('parameters',{}); arms=spec.get('arms',{'default':{}})
    require(isinstance(params,dict),'parameters must be a table')
    require(isinstance(arms,dict) and arms,'at least one arm is required')
    for k,v in params.items():
        safe_name(k,'parameter name'); json_safe(v,f'parameter {k}')
    for k,v in arms.items():
        safe_name(k,'arm name'); require(isinstance(v,dict),f'arm {k} must be a table')
        for ak,av in v.items():
            safe_name(ak,f'arm {k} key');json_safe(av,f'arm {k}.{ak}')
    require(not spec.get('paired') or len(arms)>=2,'paired experiments need at least 2 arms')
    datasets=spec.get('datasets',{})
    require(isinstance(datasets,dict),'datasets must be a table')
    for name,rel in datasets.items():
        safe_name(name,'dataset');relative_file(root,rel)
    steps=spec.get('steps',[])
    require(isinstance(steps,list) and steps,'at least one step is required')
    ids=set();step_map={}
    for st in steps:
        strict_keys(st,{'id','uses','with','out'},'step')
        sid=safe_name(st.get('id'),'step id')
        require(sid not in ids,f'duplicate step {sid}')
        ids.add(sid);step_map[sid]=st
        require(isinstance(st.get('uses'),str),'step uses must be a string')
        plugin=plugin_source(st['uses'])
        if plugin is not None:relative_file(root,plugin)
        w=st.get('with',{});o=st.get('out',{})
        require(isinstance(w,dict),'step.with must be table')
        if st['uses']=='builtin:csv_column':
            require(isinstance(w.get('path'),str) and bool(re.fullmatch(r'\$\{datasets\.[A-Za-z_][A-Za-z0-9_]*\}',w['path'])),
                    'csv_column must use a declared dataset reference for path')
        require(isinstance(o,dict) and o,'step.out must declare outputs')
        for name,typ in o.items():
            safe_name(name,'step output name'); require(typ in ('number','integer','string','boolean','array','object'),f'unknown output type {typ!r}')
        for ref in references(w):
            prefix, name, field=ref
            if prefix=='parameters':require(name in params and not field, f'unknown parameter {name}')
            elif prefix=='arm':
                require(all(name in row for row in arms.values()) and not field,f'unknown arm field {name}')
            elif prefix=='run':require(name in ('seed','replicate','arm') and not field,f'unknown run field {name}')
            elif prefix=='datasets':require(name in datasets and not field,f'unknown dataset {name}')
            elif prefix=='steps':require(name in ids or name in [x.get('id') for x in steps],f'unknown step {name}')
            if prefix=='steps':require(field and field in step_map.get(name,next((s for s in steps if s.get('id')==name),{})).get('out',{}),f'unknown step output {name}.{field}')
    # Produce deterministic topological order, detect cycles even for forward references.
    pending={st['id']:set(ref[1] for ref in references(st.get('with',{})) if ref[0]=='steps') for st in steps}
    order=[]
    while pending:
        ready=[s for s in pending if not pending[s]]
        require(ready, f'cycle among steps: {sorted(pending)}')
        for s in ready:
            order.append(step_map[s]);del pending[s]
        for dep in pending.values():dep.difference_update(ready)
    metrics=spec.get('metrics',[]);require(isinstance(metrics,list) and metrics,'at least one metric required')
    mset=set()
    for m in metrics:
        strict_keys(m,{'id','source','unit'},'metric')
        mid=safe_name(m.get('id'),'metric id');require(mid not in mset,'duplicate metric '+mid);mset.add(mid)
        ref=REF.fullmatch(m.get('source',''))
        require(ref and ref[1]=='steps' and ref[3], f'metric {mid} source needs ${{steps.ID.field}}')
        require(ref[2] in step_map and ref[3] in step_map[ref[2]]['out'],f'metric {mid} source unknown')
        require(step_map[ref[2]]['out'][ref[3]] in ('number','integer'),f'metric {mid} must be numeric')
        require(type(m.get('unit','')) is str,'metric unit must be text')
    guards=spec.get('guards',[]); require(isinstance(guards,list),'guards must be a list')
    gids=set()
    for guard in guards:
        strict_keys(guard,{'id','source','op','value'},'guard')
        gid=safe_name(guard.get('id'),'guard id');require(gid not in gids,'duplicate guard '+gid);gids.add(gid)
        match=REF.fullmatch(guard.get('source',''))
        require(match and match[1]=='steps' and match[3] and match[2] in step_map and match[3] in step_map[match[2]]['out'],
                f'guard {gid} requires valid step output reference')
        require(guard.get('op') in ('==','!=','>','>=','<','<='),'guard op invalid')
        require('value' in guard and type(guard['value']) in (int,float,bool,str),'guard comparison value must be scalar')
    claims=spec.get('claims',[]); require(isinstance(claims,list),'claims must be a list')
    clids=set()
    for c in claims:
        strict_keys(c,{'id','metric','control','treatment','direction','threshold','confidence'},'claim')
        cid=safe_name(c.get('id'),'claim id'); require(cid not in clids,'duplicate claim id');clids.add(cid)
        require(c.get('metric') in mset,f'claim {cid} references unknown metric')
        require(c.get('control') in arms and c.get('treatment') in arms and c['control']!=c['treatment'],f'claim {cid}: invalid arms')
        require(c.get('direction') in ('increase','decrease'),f'claim {cid}: invalid direction')
        require(type(c.get('threshold',0)) in (int,float) and math.isfinite(c.get('threshold',0)),'claim threshold invalid')
        require(type(c.get('confidence',0.95)) in (int,float) and 0.5<=c.get('confidence',0.95)<1,'confidence must be [0.5,1)')
    return spec,root,order

def resolve(val, ctx):
    if isinstance(val,str):
        m=REF.fullmatch(val)
        if not m:return val
        grp,name,field=m.groups()
        v=ctx[grp][name]
        return v[field] if field else v
    if isinstance(val,list):return [resolve(v,ctx) for v in val]
    if isinstance(val,dict):return {k:resolve(v,ctx) for k,v in val.items()}
    return val

def builtin(name, data, rng):
    if name=='bernoulli':
        require(set(data)=={'n','p'},'bernoulli expects n,p')
        n,p=data['n'],data['p'];require(type(n) is int and 0<=n<=10_000_000,'n must be integer 0..10M')
        require(type(p) in (float,int) and 0<=p<=1,'p must be in [0,1]')
        successes=sum(rng.random()<p for _ in range(n))
        return {'successes':successes,'total':n,'rate':successes/n if n else 0.0}
    if name=='ratio':
        require(set(data)=={'numerator','denominator'},'ratio expects numerator,denominator')
        a,b=data['numerator'],data['denominator'];require(type(a) in (int,float) and type(b) in (int,float) and b!=0,'ratio needs numerical denominator != 0')
        return {'value':a/b}
    if name=='mean':
        require(set(data)=={'values'} and isinstance(data['values'],list) and data['values'],'mean expects a nonempty list')
        return {'value':statistics.fmean(data['values']),'n':len(data['values'])}
    if name=='linear':
        require(set(data)=={'x','slope','intercept'},'linear expects x,slope,intercept')
        return {'value':data['x']*data['slope']+data['intercept']}
    if name=='csv_column':
        require(set(data)=={'path','column'},'csv_column expects path,column')
        vals=[]
        with open(data['path'],newline='',encoding='utf8') as f:
            rows=csv.DictReader(f)
            require(data['column'] in (rows.fieldnames or []),'missing column '+str(data['column']))
            for row in rows:
                try: vals.append(float(row[data['column']]))
                except (ValueError,TypeError) as ex:raise ExperimentError('non-numeric CSV value') from ex
                require(len(vals)<=1_000_000,'CSV column too long')
        require(vals,'empty CSV column')
        return {'values':vals,'n':len(vals)}
    raise ExperimentError(f'unknown builtin {name}')

def call_python(root, uses, args, seed):
    rel,fn=uses.split(':')[1:]
    path=relative_file(root,rel)
    module_name='_tev_'+filehash(path)[:16]
    # Read and compile the declared source directly: Python's .pyc timestamp/size
    # cache can otherwise execute OLD code after same-second, same-size edits.
    # Plugins are still fully trusted Python and are NEVER a sandbox.
    mod=types.ModuleType(module_name)
    mod.__file__=str(path)
    exec(compile(path.read_bytes(),str(path),'exec'),mod.__dict__)
    function=getattr(mod,fn,None)
    require(callable(function),f'plugin function {fn} not found in {rel}')
    return function(copy.deepcopy(args),seed=seed)

def execute_step(st, inputs, seed, root, allow_python):
    uses=st['uses']; rng=random.Random(seed)
    if uses.startswith('builtin:'):
        result=builtin(uses.split(':',1)[1],inputs,rng)
    else:
        require(allow_python,'Python plugins execute arbitrary code; rerun with --allow-python only for trusted experiments')
        result=call_python(root,uses,inputs,seed)
    require(isinstance(result,dict),f"step {st['id']} must return a dictionary")
    require(set(result)==set(st['out']),f"step {st['id']} outputs {sorted(result)} but declared {sorted(st['out'])}")
    for field,typ in st['out'].items():check_type(result[field],typ,st['id']+'.'+field)
    return json_safe(result,'step result')

def seed_for(base,rep,arm,paired):
    return int(digest([base,rep,None if paired else arm])[:15],16)

def percentile(vals,p):
    vals=sorted(vals)
    x=(len(vals)-1)*p
    a=int(math.floor(x));b=int(math.ceil(x))
    return vals[a]+(vals[b]-vals[a])*(x-a)

def inference(spec,observations):
    conclusions=[]; reps=spec.get('replicates',1); paired=spec.get('paired',False)
    for c in spec.get('claims',[]):
        name=c['metric'];cname=c['control'];tname=c['treatment'];threshold=c.get('threshold',0)
        direction=c['direction'];conf=c.get('confidence',0.95)
        co=[o['metrics'][name] for o in observations if o['arm']==cname]
        tr=[o['metrics'][name] for o in observations if o['arm']==tname]
        effect=statistics.fmean(tr)-statistics.fmean(co)
        observed=effect if direction=='increase' else -effect
        record={'id':c['id'],'metric':name,'control':cname,'treatment':tname,
                'observed_difference_treatment_minus_control':effect,
                'oriented_effect':observed,'threshold':threshold,
                'interval':None,'method':'percentile bootstrap (exploratory)',
                'confidence':conf,'status':'insufficient_replication'}
        if reps>=2 and len(set(co))==1 and len(set(tr))==1:
            record['method']='deterministic outputs (no sampling uncertainty estimated)'
            record['status']='computational_comparison_only'
        elif reps>=2:
            rng=random.Random(seed_for(spec.get('seed',0),347811,c['id'],False))
            bs=[]
            for _ in range(2000):
                if paired:
                    inds=[rng.randrange(reps) for i in range(reps)]
                    v=statistics.fmean((tr[i]-co[i])*(1 if direction=='increase' else -1) for i in inds)
                else:
                    t=statistics.fmean(tr[rng.randrange(reps)] for _ in range(reps))
                    a=statistics.fmean(co[rng.randrange(reps)] for _ in range(reps))
                    v=(t-a)*(1 if direction=='increase' else -1)
                bs.append(v)
            lo=percentile(bs,(1-conf)/2);hi=percentile(bs,1-(1-conf)/2)
            record['interval']=[lo,hi]
            record['status']='supported_by_interval' if lo>threshold else ('contradicted_by_interval' if hi<threshold else 'inconclusive')
        conclusions.append(record)
    return conclusions

def stable_inputs(value,dataset_paths):
    """Portable fingerprint representation: paths to declared data get logical URIs.

    The executable input remains a real path; evidence and cache keys use a
    location-independent identifier tied to the declared dataset digest.
    """
    path_names={p:'dataset://'+name for name,p in dataset_paths.items()}
    if isinstance(value,str):return path_names.get(value,value)
    if isinstance(value,list):return [stable_inputs(v,dataset_paths) for v in value]
    if isinstance(value,dict):return {k:stable_inputs(v,dataset_paths) for k,v in value.items()}
    return value

def pipeline_run(spec,root,order,cache_dir=None,no_cache=False,allow_python=False):
    ds={name:str(relative_file(root,p)) for name,p in spec.get('datasets',{}).items()}
    dsh={name:filehash(path) for name,path in ds.items()}
    psh={st['uses']:filehash(relative_file(root,plugin_source(st['uses']))) for st in order if plugin_source(st['uses'])}
    observations=[]; lineage=[]; counters={'hit':0,'miss':0}
    arms=spec.get('arms',{'default':{}})
    for rep in range(spec.get('replicates',1)):
        # Fixed randomized arm order; randomization of scheduling does not equal participant randomization.
        arm_order=list(arms)
        random.Random(seed_for(spec.get('seed',0),rep,'arm_order',False)).shuffle(arm_order)
        for arm in arm_order:
            seed=seed_for(spec.get('seed',0),rep,arm,spec.get('paired',False))
            ctx={'parameters':spec.get('parameters',{}),'arm':arms[arm],
                 'run':{'seed':seed,'replicate':rep,'arm':arm},'datasets':ds,'steps':{}}
            per_steps=[]
            for i,st in enumerate(order):
                inputs=resolve(st.get('with',{}),ctx)
                json_safe(inputs,'resolved input')
                portable_inputs=stable_inputs(inputs,ds)
                step_seed=seed_for(seed,i,st['id'],False)
                key=digest({'version':VERSION,'step':st,'inputs':portable_inputs,'step_seed':step_seed,
                            'source':psh.get(st['uses']),'datasets':dsh,'python':list(sys.version_info[:3])})
                cache_file=cache_dir/(key+'.json') if cache_dir else None
                # Caches never bypass execution authorization for Python plugins.
                if st['uses'].startswith('python:') and not allow_python:
                    raise ExperimentError('Python plugins need explicit --allow-python, even on a cache hit')
                if cache_file and cache_file.is_file() and not no_cache:
                    # Cache checks key, integrity checksum, and output type contract.
                    try:
                        wrapper=json.loads(cache_file.read_text(encoding='utf8'))
                        require(wrapper['key']==key and wrapper['digest']==digest(wrapper['result']),'corrupt cache integrity')
                        result=wrapper['result']
                        require(set(result)==set(st['out']),'corrupt cache output keys')
                        for field,typ in st['out'].items():check_type(result[field],typ,'cache')
                        hit=True
                    except (ValueError,ExperimentError,KeyError,TypeError):
                        result=execute_step(st,inputs,step_seed,root,allow_python);hit=False
                else:
                    result=execute_step(st,inputs,step_seed,root,allow_python);hit=False
                counters['hit' if hit else 'miss']+=1
                if cache_file and not hit:
                    cache_file.parent.mkdir(parents=True,exist_ok=True)
                    temp=cache_file.with_name(cache_file.name+'.'+str(os.getpid())+'.tmp')
                    temp.write_text(canonical({'key':key,'digest':digest(result),'result':result}),encoding='utf8');os.replace(temp,cache_file)
                ctx['steps'][st['id']]=result
                per_steps.append({'id':st['id'],'uses':st['uses'],'input_digest':digest(portable_inputs),
                                  'output_digest':digest(result),'cache_key':key,'cache_hit':hit,
                                  'inputs':portable_inputs,'outputs':result})
            metrics={m['id']:resolve(m['source'],ctx) for m in spec['metrics']}
            for k,v in metrics.items():check_type(v,'number','metric '+k)
            guard_results={}
            for g in spec.get('guards',[]):
                v=resolve(g['source'],ctx);w=g['value'];op=g['op']
                try:
                    ok={'==':lambda:v==w,'!=':lambda:v!=w,'>':lambda:v>w,'>=':lambda:v>=w,'<':lambda:v<w,'<=':lambda:v<=w}[op]()
                except TypeError as ex: raise ExperimentError(f'guard {g["id"]} compares incompatible types') from ex
                require(ok, f'guard {g["id"]} failed at arm={arm}, replicate={rep}: {v!r} {op} {w!r}')
                guard_results[g['id']]='passed'
            observations.append({'arm':arm,'replicate':rep,'seed':seed,'metrics':metrics,'guards':guard_results})
            lineage.append({'arm':arm,'replicate':rep,'steps':per_steps})
    observations.sort(key=lambda o:(o['replicate'],o['arm']))
    lineage.sort(key=lambda o:(o['replicate'],o['arm']))
    return observations,lineage,counters,dsh,psh

def save_json(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,indent=2,sort_keys=True,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf8')

def run(path,out,allow_python=False,no_cache=False,cache=None):
    spec,root,order=load_spec(path)
    output=Path(out).resolve()
    require(not output.exists(),f'output exists (refusing to overwrite): {output}')
    # Write to a staging directory. Publish only a successful complete run.
    staging=output.with_name(output.name+'.tmp-'+str(os.getpid()))
    require(not staging.exists(),f'temporary output exists: {staging}')
    cache_dir=Path(cache).resolve() if cache else None
    try:
        staging.mkdir(parents=True)
        obs,lineage,counts,dsh,psh=pipeline_run(spec,root,order,cache_dir,no_cache,allow_python)
        claims=inference(spec,obs)
        # Do not advertise scientific verification on the mere absence of a claim.
        if not claims:verdict='unverified_no_claims'
        elif any(c['status']=='contradicted_by_interval' for c in claims):verdict='evidence_against_claim'
        elif all(c['status']=='supported_by_interval' for c in claims):verdict='claims_supported_exploratory'
        else:verdict='inconclusive'
        snapshot=staging/'source'
        snapshot.mkdir()
        shutil.copy2(path,snapshot/'experiment.tev')
        for rel in list(spec.get('datasets',{}).values())+list({p for p in (plugin_source(st['uses']) for st in order) if p}):
            src=relative_file(root,rel);dest=snapshot/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dest)
        report={'version':VERSION,'title':spec['title'],'protocol_sha256':filehash(path),
                'inputs_sha256':dsh,'plugins_sha256':psh,
                'metric_units':{m['id']:m.get('unit','') for m in spec['metrics']},
                'environment':{'python':platform.python_version(),'implementation':platform.python_implementation(),
                               'platform':platform.platform()},
                'design':{'replicates':spec.get('replicates',1),'paired':spec.get('paired',False),'seed':spec.get('seed',0),'arms':list(spec.get('arms',{'default':{}}))},
                'guard_count':len(spec.get('guards',[])),
                'observations':obs,'claims':claims,'verdict':verdict,
                'limitations':['Bootstrap intervals are exploratory; neither causal identification nor scientific truth is automatically proven.',
                               'Reproducibility depends on all external services, packages and Python-plugin behavior.',
                               'Python plugins are trusted code; TEVIEW does not sandbox them.']}
        save_json(staging/'report.json',report)
        save_json(staging/'lineage.json',{'steps':lineage,'cache':counts,'order':[s['id'] for s in order]})
        save_json(staging/'protocol.json',spec)
        fields=['arm','replicate','seed']+[m['id'] for m in spec['metrics']]
        with open(staging/'measurements.csv','w',encoding='utf8',newline='') as f:
            w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
            for o in obs:w.writerow({**{k:o[k] for k in ('arm','replicate','seed')},**o['metrics']})
        text=['# '+spec['title'],'',f'**Verdict:** {verdict}',f'**Replications:** {spec.get("replicates",1)} per arm',
              f'**Protocol SHA-256:** `{report["protocol_sha256"]}`','',
              '## Evidence', '']
        if claims:
            for c in claims:text.append(f'- **{c["id"]}**: effect={c["oriented_effect"]:.6g}, interval={c["interval"]}, status={c["status"]}')
        else:text.append('No hypotheses declared. No scientific claim was tested.')
        text+=['','## Interpretation','The engine records a computational result, not proof of scientific validity.',
               'Synthetic simulations do not establish an effect in real participants or physical instruments.',
               'The source bundle allows local replay if all plugins and dependencies are available.','']
        (staging/'REPORT.md').write_text('\n'.join(text),encoding='utf8')
        output.parent.mkdir(parents=True,exist_ok=True)
        staging.rename(output)
        return report,counts
    except Exception:
        shutil.rmtree(staging,ignore_errors=True)
        raise

def verify(folder,allow_python=False):
    folder=Path(folder).resolve()
    if (folder/'capture.json').is_file():
        from teview_capture import verify_capture
        return verify_capture(folder)
    report=json.loads((folder/'report.json').read_text())
    spec_path=folder/'source'/'experiment.tev'
    require(spec_path.is_file(),'run has no source snapshot')
    require(filehash(spec_path)==report['protocol_sha256'],'protocol copy was modified')
    spec,root,order=load_spec(spec_path)
    ds_now={name:filehash(relative_file(root,rel)) for name,rel in spec.get('datasets',{}).items()}
    require(ds_now==report['inputs_sha256'],'declared dataset snapshots have changed')
    code_now={st['uses']:filehash(relative_file(root,plugin_source(st['uses']))) for st in order if plugin_source(st['uses'])}
    require(code_now==report['plugins_sha256'],'plugin snapshots have changed')
    obs,replay_lineage,*_=pipeline_run(spec,root,order,None,True,allow_python)
    recorded_lineage=json.loads((folder/'lineage.json').read_text(encoding='utf8'))['steps']
    def without_cache_status(items):
        return [{**r,'steps':[{k:v for k,v in s.items() if k!='cache_hit'} for s in r['steps']]} for r in items]
    require(without_cache_status(replay_lineage)==without_cache_status(recorded_lineage),
            'replay DIFFERED from recorded stage inputs/outputs')
    require(obs==report['observations'],'replay DIFFERED from recorded measurements')
    require(inference(spec,obs)==report['claims'],'replay DIFFERED from recorded claims')
    require(report.get('design') == {'replicates':spec.get('replicates',1), 'paired':spec.get('paired',False),
            'seed':spec.get('seed',0), 'arms':list(spec.get('arms',{'default':{}}))}, 'reported experimental design was modified')
    claims = inference(spec,obs)
    expected_verdict = ('unverified_no_claims' if not claims else
        'evidence_against_claim' if any(c['status']=='contradicted_by_interval' for c in claims) else
        'claims_supported_exploratory' if all(c['status']=='supported_by_interval' for c in claims) else 'inconclusive')
    require(report.get('verdict') == expected_verdict, 'reported verdict was modified')
    require(report.get('guard_count') == len(spec.get('guards', [])), 'reported guard count was modified')
    if 'metric_units' in report:
        require(report['metric_units'] == {m['id']:m.get('unit','') for m in spec['metrics']},
                'reported metric units were modified')
    return {'verified_replay':True,'observation_count':len(obs),'protocol_sha256':report['protocol_sha256'],
            'interpretation':'computational replay only; not scientific validation'}

def compare(a,b):
    x=json.loads((Path(a)/'report.json').read_text());y=json.loads((Path(b)/'report.json').read_text())
    def av(report):
        d={}
        for o in report['observations']:
            for k,v in o['metrics'].items():d.setdefault((o['arm'],k),[]).append(v)
        return {f'{k[0]}.{k[1]}':statistics.fmean(v) for k,v in d.items()}
    av1=av(x);av2=av(y)
    return {'left':x['title'],'right':y['title'],
            'same_protocol':x['protocol_sha256']==y['protocol_sha256'],
            'metric_means':{k:{'left':av1.get(k),'right':av2.get(k),
                    'difference':av2[k]-av1[k] if k in av1 and k in av2 else None} for k in sorted(set(av1)|set(av2))}}

def plan(path):
    spec,root,order=load_spec(path)
    return {'title':spec['title'],'steps':[{'id':s['id'],'uses':s['uses'],'dependencies':sorted({r[1] for r in references(s.get('with',{})) if r[0]=='steps'})} for s in order],
            'arms':list(spec.get('arms',{'default':{}})),'replicates':spec.get('replicates',1),
            'total_step_invocations':len(order)*len(spec.get('arms',{'default':{}}))*spec.get('replicates',1),
            'python_plugins':sorted({s['uses'] for s in order if s['uses'].startswith('python:')}),
            'declared_datasets':spec.get('datasets',{}),'declared_hypotheses':[x['id'] for x in spec.get('claims',[])],
            'guards':[x['id'] for x in spec.get('guards',[])]}

def main(argv=None):
    parser=argparse.ArgumentParser(prog='tev',description='TEVIEW: experiment protocols with inspectable evidence')
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('validate');p.add_argument('protocol')
    p=sub.add_parser('plan');p.add_argument('protocol')
    p=sub.add_parser('run');p.add_argument('protocol');p.add_argument('--out',required=True)
    p.add_argument('--allow-python',action='store_true',help='execute trusted local Python plugins')
    p.add_argument('--cache',help='optional shared stage cache directory');p.add_argument('--no-cache',action='store_true')
    p=sub.add_parser('verify');p.add_argument('run_folder');p.add_argument('--allow-python',action='store_true')
    p=sub.add_parser('compare');p.add_argument('left');p.add_argument('right')
    p=sub.add_parser('capture', help='Capture an existing command with declared inputs and numeric metrics')
    p.add_argument('--out',required=True);p.add_argument('--root',default='.')
    p.add_argument('--code',action='append',default=[],help='source file to snapshot (repeatable)')
    p.add_argument('--data',action='append',default=[],help='input dataset to snapshot (repeatable)')
    p.add_argument('--metrics',default='metrics.json',help='JSON file the command must produce')
    p.add_argument('--artifact',action='append',default=[],help='output artifact to hash (repeatable)')
    p.add_argument('--timeout',type=int,default=60);p.add_argument('--seed',type=int,default=0)
    p.add_argument('argv_command',nargs=argparse.REMAINDER)
    p=sub.add_parser('scene-check', help='Check a composable physical scene and its units')
    p.add_argument('scene')
    p=sub.add_parser('scene-explain', help='List automatic physical interactions in a scene')
    p.add_argument('scene')
    p=sub.add_parser('simulate', help='Compile and simulate a composable physical scene')
    p.add_argument('scene');p.add_argument('--out',required=True)
    p=sub.add_parser('scene-converge', help='Check time-step sensitivity of a physical scene')
    p.add_argument('scene')
    p.add_argument('--rtol',type=float,default=1e-3,help='relative final-state refinement tolerance')
    p.add_argument('--atol',type=float,default=1e-6,help='absolute SI-unit final-state tolerance')
    p.add_argument('--json-out',help='optional path for the diagnostic JSON')
    p=sub.add_parser('scene-verify', help='Replay and verify a saved physical scene')
    p.add_argument('run_folder')
    p=sub.add_parser('visualize', help='Generate a self-contained HTML viewer for a saved physical scene')
    p.add_argument('run_folder');p.add_argument('--out',help='HTML output path (default: run_folder/viewer.html)')
    p.add_argument('--verify-evidence',action='store_true',help='Replay and verify saved simulation before rendering')
    p=sub.add_parser('init', help='Create an editable Python experiment starter')
    p.add_argument('directory')
    p=sub.add_parser('gate', help='Evaluate a candidate run against a versioned regression policy')
    p.add_argument('baseline');p.add_argument('candidate');p.add_argument('--policy',required=True)
    p.add_argument('--allow-protocol-change',action='store_true')
    p.add_argument('--allow-input-change',action='store_true')
    p.add_argument('--json-out',help='Write machine-readable gate results')
    p.add_argument('--verify-evidence',action='store_true',
                   help='Re-execute and verify both bundles before evaluating (executes capture commands)')
    p.add_argument('--allow-python',action='store_true',
                   help='Permit trusted Python plugins when --verify-evidence is enabled')
    args=parser.parse_args(argv)
    try:
        if args.command in ('validate','plan'):
            info=plan(args.protocol)
            print('VALID '+info['title'] if args.command=='validate' else json.dumps(info,indent=2))
        elif args.command=='run':
            result,cache=run(args.protocol,args.out,args.allow_python,args.no_cache,args.cache)
            print(json.dumps({'out':str(args.out),'verdict':result['verdict'],'claims':result['claims'],'cache':cache},indent=2))
        elif args.command=='verify':print(json.dumps(verify(args.run_folder,args.allow_python),indent=2))
        elif args.command=='compare':print(json.dumps(compare(args.left,args.right),indent=2))
        elif args.command=='capture':
            from teview_capture import capture
            command_args = args.argv_command
            if command_args and command_args[0]=='--':command_args=command_args[1:]
            print(json.dumps(capture(args.root,args.out,code=args.code,data=args.data,
                     command=command_args,metrics=args.metrics,artifacts=args.artifact,
                     timeout=args.timeout,seed=args.seed),indent=2))
        elif args.command in ('scene-check','scene-explain','simulate','scene-verify'):
            from teview_physics import load_scene, simulate, verify_scene
            if args.command=='scene-verify':
                print(json.dumps(verify_scene(args.run_folder),indent=2))
            else:
                model=load_scene(args.scene)
                if args.command=='scene-check':
                    print(json.dumps({'status':'compiled','components':len(model.components),
                                      'interactions':len(model.interactions)},indent=2))
                elif args.command=='scene-explain':
                    print(json.dumps({'title':model.title,'components':model.components,
                                      'interactions':model.interactions},indent=2))
                else:
                    result,_=simulate(model,args.out)
                    from pathlib import Path as _Path
                    (_Path(args.out)/'scene.tev').write_bytes(_Path(args.scene).read_bytes())
                    print(json.dumps({'status':result['status'], 'output':args.out,
                                      'interactions':len(model.interactions),
                                      'final':result['final']},indent=2))
        elif args.command=='scene-converge':
            from teview_physics import load_scene
            from teview_accuracy import check_convergence
            result=check_convergence(load_scene(args.scene),relative_tolerance=args.rtol,
                                     absolute_tolerance=args.atol)
            if args.json_out:save_json(Path(args.json_out),result)
            print(json.dumps(result,indent=2))
            return 0 if result['status']=='refinement_stable' else 2
        elif args.command=='visualize':
            from teview_visual import render_scene
            result = render_scene(args.run_folder, args.out) if not args.verify_evidence else None
            if args.verify_evidence:
                from teview_physics import verify_scene
                verification = verify_scene(args.run_folder)
                result = render_scene(args.run_folder, args.out)
                result['verification'] = verification['status']
            print(json.dumps(result,indent=2))
        elif args.command=='init':
            from teview_starter import create_starter
            print(json.dumps(create_starter(args.directory),indent=2))
        elif args.command=='gate':
            from teview_gate import gate, GateError
            if args.verify_evidence:
                verify(args.baseline,args.allow_python)
                verify(args.candidate,args.allow_python)
            result=gate(args.baseline,args.candidate,args.policy,args.allow_protocol_change,args.allow_input_change)
            if args.json_out:save_json(Path(args.json_out),result)
            print(json.dumps(result,indent=2))
            return 0 if result['status']=='pass' else 2
    except (ExperimentError,OSError,ValueError,KeyError,TypeError) as exc:
        print(f'TEVIEW ERROR: {exc}',file=sys.stderr);return 1
    return 0

if __name__=='__main__':raise SystemExit(main())
