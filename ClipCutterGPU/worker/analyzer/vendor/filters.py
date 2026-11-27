"""Reversible heuristics on stored observations; no inference on filter changes."""
import numpy as np
DEFAULTS={'background':True,'static':True,'min_face':40,'confidence':.60,'min_duration':1.,'regions':[]}
def static_overlay(g, duration):
    obs=sorted((o for o in g['observations'] if 'box_norm' in o and 'signature' in o),key=lambda o:o['time'])
    if len(obs)<6 or duration<4: return False
    if obs[-1]['time']-obs[0]['time']<max(3,duration*.65): return False
    b=np.asarray([o['box_norm'] for o in obs]); median=np.median(b,axis=0); x,y,X,Y=median
    if not ((x<.2 or X>.8) and (y<.2 or Y>.8) and X-x<.25 and Y-y<.25): return False
    stable=(np.max(abs(b-median),axis=1)<.012).mean()
    sig=np.asarray([o['signature'] for o in obs],dtype=float); delta=np.mean(abs(sig-np.median(sig,axis=0)),axis=1)
    return stable>=.9 and (delta<5).mean()>=.9

def filter_observations(g,data,intervals):
    f={**DEFAULTS,**data.get('filters',{})} if 'filters' in data else {'background':False,'static':False,'regions':[]}
    obs=g['observations']; reasons=[]
    if any(not o.get('dominance_accepted',True) for o in obs):reasons.append('Non-dominant or similarly sized faces')
    obs=[o for o in obs if o.get('dominance_accepted',True)]
    if g.get('force_include'):return list(obs),[]
    if f.get('static') and static_overlay(g,data['duration']): return [],reasons+['Static corner portrait (estimated)']
    active=[]
    for o in obs:
        if f.get('background') and (o.get('face_size',1e9)<f['min_face'] or o.get('confidence',1)<f['confidence']):
            reasons.append('Small / low-confidence face'); continue
        if 'box_norm' in o:
            x,y,X,Y=o['box_norm']; cx=(x+X)/2;cy=(y+Y)/2
            if any(a<=cx<=c and b<=cy<=d for a,b,c,d in f.get('regions',[])):
                reasons.append('Excluded screen region');continue
        active.append(o)
    if f.get('background'):
        segments=intervals([o['time'] for o in active],data['duration'],data['sample_interval'])
        keep=[(a,b) for a,b in segments if b-a+1e-5>=f['min_duration']]
        old=len(active); active=[o for o in active if any(a-.001<=o['time']<=b+.001 for a,b in keep)]
        if len(active)<old: reasons.append('Short appearance')
    return active, sorted(set(reasons))

def diverse_refs(obs,limit=15):
    out=[]
    for o in sorted(obs,key=lambda o:o['quality'],reverse=True):
        if any(abs(o['time']-p['time'])<1.5 or ('signature' in o and 'signature' in p and np.mean(abs(np.asarray(o['signature'],float)-np.asarray(p['signature'],float)))<5) for p in out): continue
        out.append(o)
        if len(out)>=limit: break
    return [o['image'] for o in out]
