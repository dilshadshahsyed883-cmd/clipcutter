"""Anonymous, video-local dominance policy. Compare bounding-box area, not width."""
def selected_indices(boxes,ratio):
    areas=[max(0,b[2]-b[0])*max(0,b[3]-b[1]) for b in boxes]
    ranked=sorted((i for i,a in enumerate(areas) if a>0),key=lambda i:(-areas[i],i))
    if not ranked:return set(),"no_face"
    if len(ranked)==1:return {ranked[0]},"single"
    if areas[ranked[0]]>=ratio*areas[ranked[1]]:return {ranked[0]},"dominant"
    return set(),"similar_size"

def subtract_ranges(ranges,excluded):
    out=[]
    for start,end in ranges:
        pos=start
        for a,b in excluded:
            if b<=pos:continue
            if a>=end:break
            if a>pos:out.append([pos,min(a,end)])
            pos=max(pos,b)
            if pos>=end:break
        if pos<end:out.append([pos,end])
    return [[round(a,3),round(b,3)] for a,b in out if b>a]
