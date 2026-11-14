import sys, collections, json, os
def ents(path):
    L=open(path, encoding='utf-8', errors='replace').read().splitlines()
    pairs=[(L[i].strip(), L[i+1]) for i in range(0, len(L)-1, 2)]
    out=[]; sec=None; cur=None; inblk=False
    for i,(c,v) in enumerate(pairs):
        if c=='0' and v=='SECTION': sec=pairs[i+1][1]; continue
        if sec not in ('ENTITIES','BLOCKS'): continue
        if c=='0':
            if cur: out.append(cur)
            cur={'type':v,'sec':sec}
        elif cur is not None:
            if c in ('8','2','1'): cur.setdefault(c, v)
    if cur: out.append(cur)
    return out
p=sys.argv[1]
E=[e for e in ents(p) if e['sec']=='ENTITIES']
print(collections.Counter((e.get('8'), e['type']) for e in E).most_common(40))
print('INSERT blocks', collections.Counter((e.get('8'), e.get('2')) for e in E if e['type']=='INSERT').most_common(40))
txt=[(e.get('8'), e.get('1')) for e in E if e['type'] in ('TEXT','MTEXT')]
print('texts', len(txt), txt[:60])
