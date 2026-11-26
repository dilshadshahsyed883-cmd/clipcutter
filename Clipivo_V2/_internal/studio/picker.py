# SPDX-License-Identifier: AGPL-3.0-or-later
"""Video-only adaptation of Concat C Builder/planning.rs selection logic.

Preserves xorshift seed, group-first weighted draws, inverse usage weighting,
source cooldown, source trim randomization. Adds strict feasible min/max duration
bounds so the final short remainder cannot silently break the user's minimum.
"""
import math,re,copy
MASK=(1<<64)-1
class Random:
    def __init__(self,seed):self.state=int(seed)&MASK or 0x9e3779b97f4a7c15
    def unit(self):
        x=self.state;x^=(x<<13)&MASK;x^=x>>7;x^=(x<<17)&MASK;self.state=x&MASK
        return (self.state>>11)/(1<<53)

def keyword(path):
    from pathlib import Path
    s=Path(path).stem;v=re.sub(r'[ _-]*[0-9]+$','',s);return v or s

def draw(rng,items,weights):
    total=sum(weights)
    if total<=0:raise ValueError('All selection weights are zero')
    ticket=rng.unit()*total
    for item,w in zip(items,weights):
        ticket-=w
        if ticket<0:return item
    return items[-1]

def bounded_parts(length,minimum,maximum):
    length=round(float(length)*1e6);lo=round(minimum*1e6);hi=round(maximum*1e6)
    if lo<=0 or hi<lo:raise ValueError('Clip durations must satisfy 0 < minimum ≤ maximum')
    if length<lo:return []
    n=math.ceil(length/hi)
    if length//n>=lo:
        out=[];at=0
        for i in range(n):
            end=round(length*(i+1)/n);out.append((at/1e6,end/1e6));at=end
        return out
    # An impossible small tail is discarded explicitly, never added to a max-size cut.
    return [(i*hi/1e6,(i+1)*hi/1e6) for i in range(length//hi)]

def constrain_ranges(ranges,minimum,maximum):
    out=[];discarded=0
    for a,b in ranges:
        pieces=bounded_parts(b-a,minimum,maximum);out.extend((a+x,a+y) for x,y in pieces);discarded+=b-a-sum(y-x for x,y in pieces)
    return out,discarded

def build_picked_plan(reference,media,minimum=2.5,maximum=4.,seed=1,cooldown=2,allow_repeats=True,group_weights=None):
    if not math.isfinite(minimum) or not math.isfinite(maximum) or not 0<minimum<=maximum:raise ValueError('Clip durations must satisfy 0 < minimum ≤ maximum')
    total=round(reference['duration']*1e6);lo=round(minimum*1e6);hi=round(maximum*1e6)
    if total<=0 or total>86400*1e6:raise ValueError('Timeline length must be between 0 and 24 hours')
    least=math.ceil(total/hi);most=total//lo
    if least>most:raise ValueError('This total duration cannot be covered within minimum/maximum clip lengths. Adjust limits.')
    rng=Random(seed);count=least+int(rng.unit()*(most-least+1));sources=[]
    for m in media:
        for i,s in enumerate(m['scenes']):
            available=round((s['end']-s['start'])*1e6)
            group=keyword(m['path']);weight=(group_weights or {}).get(group,1 if not group_weights else 0)
            if available>=lo and weight>0:sources.append(dict(path=m['path'],scene=i,start=s['start'],end=s['end'],available=available,group=group,weight=float(weight),used=int(m.get('used_count',0))))
    if not sources:raise ValueError('No footage long enough for the minimum clip length')
    uses=[0]*len(sources);recent=[];rows=[];at=0;warnings=[]
    for i in range(count):
        remaining=total-at;left=count-i;lower=max(lo,remaining-(left-1)*hi);upper=min(hi,remaining-(left-1)*lo)
        candidates=[j for j,s in enumerate(sources) if s['available']>=lower and (allow_repeats or uses[j]==0)]
        if not candidates:raise ValueError(f'Source/repeat constraints exhausted at {at/1e6:.3f}s. Enable repeats, add footage or change durations.')
        fresh=[j for j in candidates if sources[j]['path'] not in recent[-cooldown:]] if cooldown else candidates
        if fresh:candidates=fresh
        elif cooldown and recent:
            warning='Source cooldown relaxed because no unused candidate is available'
            if warning not in warnings:warnings.append(warning)
        groups=sorted({sources[j]['group'] for j in candidates})
        # Group-first selection prevents a larger folder from multiplying its desired share.
        selected_group=draw(rng,groups,[next(s['weight'] for s in sources if s['group']==g) for g in groups]);candidates=[j for j in candidates if sources[j]['group']==selected_group]
        picked=draw(rng,candidates,[1/((1+sources[j]['used'])*(1+uses[j])) for j in candidates]);s=sources[picked]
        upper=min(upper,s['available']);duration=lower+round(rng.unit()*(upper-lower));trim=s['start']+int(rng.unit()*(s['available']-duration))/1e6
        original=dict(start=at/1e6,end=(at+duration)/1e6,people=[],visual=[0.]*128,activity='',framing='',environment='',angle='')
        selected=dict(path=s['path'],scene=s['scene'],start=s['start'],end=s['end'],trim_start=trim,score=None,picked=True)
        rows.append(dict(original=original,selected=selected,candidates=[],approved=False,manual_review=True));at+=duration;uses[picked]+=1;recent.append(s['path'])
    ref=copy.deepcopy(reference);ref['scenes']=[r['original'] for r in rows]
    return dict(version=1,reference=ref,rows=rows,mode='concat_picker',picker=dict(minimum=minimum,maximum=maximum,seed=seed,cooldown=cooldown,allow_repeats=allow_repeats),warnings=warnings)
