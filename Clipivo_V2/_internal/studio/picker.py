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
    length=round(float(length)*1e6);lo=math.ceil(minimum*1e6-1e-8);hi=math.floor(maximum*1e6+1e-8)
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

def build_picked_plan(reference, media, minimum=2.5, maximum=4., seed=1,
                      cooldown=2, allow_repeats=True, group_weights=None):
    if not all(math.isfinite(v) for v in (minimum, maximum, reference['duration'])) or not 0 < minimum <= maximum:
        raise ValueError('Clip durations must satisfy 0 < minimum ≤ maximum')
    scale = float(reference.get('fps') or 1e6)
    if not math.isfinite(scale) or scale <= 0:
        raise ValueError('Invalid reference frame rate')
    total = round(reference['duration']*scale)
    if abs(total/scale-reference['duration']) > 1e-6:
        raise ValueError('Reference duration is not representable on its frame grid')
    lo, hi = math.ceil(minimum*scale-1e-8), math.floor(maximum*scale+1e-8)
    if lo <= 0 or hi < lo or not 0 < reference['duration'] <= 86400:
        raise ValueError('Invalid timeline or clip limits')
    if cooldown < 0:
        raise ValueError('Cooldown must be nonnegative')
    sources = []
    for m in sorted(media, key=lambda x: x['path']):
        for i, scene in enumerate(m['scenes']):
            available = math.floor((scene['end']-scene['start'])*scale+1e-7)
            group = keyword(m['path'])
            weight = float((group_weights or {}).get(group, 0 if group_weights else 1))
            if not math.isfinite(weight) or weight < 0:
                raise ValueError('Invalid keyword weight')
            if available >= lo and weight > 0:
                sources.append(dict(path=m['path'], scene=i, start=scene['start'],
                    end=scene['end'], cap=min(available, hi), available=available,
                    group=group, weight=weight, used=max(0,int(m.get('used_count',0)))))
    if not sources:
        raise ValueError('No eligible footage long enough for the minimum clip length')
    caps = sorted((s['cap'] for s in sources), reverse=True)
    prefix = [0]
    for c in caps:
        prefix.append(prefix[-1]+c)
    least = math.ceil(total/caps[0])
    most = total//lo
    if not allow_repeats:
        most = min(most, len(caps))
    feasible = [n for n in range(least, min(most,100000)+1)
                if allow_repeats or prefix[n] >= total]
    if not feasible:
        raise ValueError('Total duration cannot be covered within clip limits and source/repeat constraints')
    rng = Random(seed)
    count = feasible[int(rng.unit()*len(feasible))]
    uses = [0]*len(sources)
    recent, rows, warnings = [], [], []
    at = 0
    for i in range(count):
        remaining, left = total-at, count-i-1
        available_ids = [j for j in range(len(sources)) if allow_repeats or not uses[j]]
        ordered = sorted(available_ids, key=lambda j: -sources[j]['cap'])
        top = ordered[:left]
        future = sum(sources[j]['cap'] for j in top)
        top_set = set(top)
        spare = sources[ordered[left]]['cap'] if left < len(ordered) else 0
        bounds = {}
        for j in available_ids:
            capacity = left*caps[0] if allow_repeats else future-(sources[j]['cap']-spare if j in top_set else 0)
            if not allow_repeats and len(ordered)-1 < left:
                continue
            lower = max(lo, remaining-capacity)
            upper = min(sources[j]['cap'], remaining-left*lo)
            if lower <= upper:
                bounds[j] = (lower,upper)
        if not bounds:
            raise ValueError('No feasible source allocation remains')
        candidates = list(bounds)
        fresh = [j for j in candidates if sources[j]['path'] not in recent[-cooldown:]] if cooldown else candidates
        if fresh:
            candidates = fresh
        elif cooldown and recent and not warnings:
            warnings.append('Source cooldown relaxed to preserve a feasible duration')
        groups = sorted({sources[j]['group'] for j in candidates})
        group = draw(rng,groups,[next(sources[j]['weight'] for j in candidates if sources[j]['group']==g) for g in groups])
        candidates = [j for j in candidates if sources[j]['group']==group]
        j = draw(rng,candidates,[1/((1+sources[j]['used'])*(1+uses[j])) for j in candidates])
        s = sources[j]
        lower, upper = bounds[j]
        duration = lower+round(rng.unit()*(upper-lower))
        trim = s['start']+int(rng.unit()*(s['available']-duration))/scale
        original = dict(start=at/scale,end=(at+duration)/scale,people=[],visual=[0.]*128,activity='',framing='',environment='',angle='')
        selected = dict(path=s['path'],scene=s['scene'],start=s['start'],end=s['end'],
                        trim_start=trim,target_duration=duration/scale,speed=1.,score=None,picked=True)
        rows.append(dict(original=original,selected=selected,candidates=[],approved=False,manual_review=True,identity_required=[]))
        at += duration
        uses[j] += 1
        recent.append(s['path'])
    # Retain actual reference scenes; the new timeline is represented by rows only.
    return dict(version=1,reference=copy.deepcopy(reference),rows=rows,mode='concat_picker',
                picker=dict(minimum=minimum,maximum=maximum,seed=seed,cooldown=cooldown,
                            allow_repeats=allow_repeats,group_weights=group_weights),warnings=warnings)
