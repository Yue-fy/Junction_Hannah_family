import sys, json, re, collections, random
D=sys.argv[1]
def ents(path):
    L=open(path, encoding='utf-8', errors='replace').read().splitlines()
    pairs=[(L[i].strip(), L[i+1].strip()) for i in range(0, len(L)-1, 2)]
    out=[]; sec=None; cur=None
    for i,(c,v) in enumerate(pairs):
        if c=='0' and v=='SECTION': sec=pairs[i+1][1]; continue
        if sec!='ENTITIES': continue
        if c=='0':
            if cur: out.append(cur)
            cur={'type':v,'pts':[]}
        elif cur is not None:
            if c in ('8','1'): cur.setdefault(c, v)
            elif c=='10': cur['pts'].append([float(v),None])
            elif c=='20' and cur['pts'] and cur['pts'][-1][1] is None: cur['pts'][-1][1]=float(v)
    if cur: out.append(cur)
    return out
def parea(P):
    return abs(sum(P[i][0]*P[(i+1)%len(P)][1]-P[(i+1)%len(P)][0]*P[i][1] for i in range(len(P))))/2
def inside(pt,P):
    x,y=pt; c=False
    for i in range(len(P)):
        x1,y1=P[i]; x2,y2=P[(i+1)%len(P)]
        if (y1>y)!=(y2>y) and x < x1+(y-y1)*(x2-x1)/(y2-y1): c=not c
    return c
rows=[json.loads(l) for l in open(D+'/questions.jsonl') if 'swiss_dwellings' in l]
byf=collections.defaultdict(list)
for r in rows: byf[r['path']].append(r)
random.seed(0); files=random.sample(sorted(byf), 150)
stat=collections.Counter(); bad=[]
for f in files:
    E=ents(D+'/'+f.replace('.pdf','.dxf'))
    polys=[e['pts'] for e in E if e['type']=='LWPOLYLINE' and e.get('8')=='ROOM_OUTLINE']
    nums={e['1']:e['pts'][0] for e in E if e['type']=='TEXT' and e.get('8')=='ROOM_TEXT' and re.fullmatch(r'\d+\.\d+', e.get('1',''))}
    for r in byf[f]:
        m=re.search(r'(?:room|Raum|pièce|locale|stanza)\s+(\d+\.\d+)', r['question'])
        if r['type']!='area' or not m: continue
        n=m.group(1)
        if n not in nums: stat['num_text_missing']+=1; continue
        cand=[P for P in polys if inside(nums[n],P)]
        if not cand: stat['no_poly']+=1; continue
        a=min(parea(P) for P in cand)
        for scale in (1,1e-4,1e-6):
            if abs(a*scale-r['answer'])<=0.02*r['answer']: stat[f'ok_scale_{scale}']+=1; break
        else: stat['wrong']+=1; bad.append((f.split('/')[-1],n,round(a,3),r['answer']))
print(stat); print(bad[:12])
