import sys, json, re, collections, random
sys.argv=[sys.argv[0], sys.argv[1]]
exec(open('swiss_poly_check.py').read().split('rows=')[0])
rows=[json.loads(l) for l in open(D+'/questions.jsonl') if 'swiss_dwellings' in l]
byf=collections.defaultdict(list)
for r in rows: byf[r['path']].append(r)
random.seed(1); files=random.sample(sorted(byf), 150)
st=collections.Counter(); ex=collections.defaultdict(list)
for f in files:
    E=ents(D+'/'+f.replace('.pdf','.dxf'))
    c=collections.Counter((e.get('8'),e['type']) for e in E)
    labels=collections.Counter(e.get('1') for e in E if e['type']=='TEXT' and e.get('8')=='ROOM_TEXT')
    for r in byf[f]:
        q=r['question']; a=r['answer']; k=None; pred=None
        if r['type']!='count': continue
        if re.search(r'apartments|Wohnungen|appartements|appartamenti', q): k='apartments'; pred=c[('UNIT_OUTLINE','LWPOLYLINE')]
        elif re.search(r'doors|Türen|portes|porte', q): k='doors'; pred=c[('DOOR','ARC')]
        elif re.search(r'windows|Fenster|fenêtres|finestre', q): k='windows'; pred=c[('WINDOW','LWPOLYLINE')]/3
        else:
            m=re.search(r"['«‘\"](.+?)['»’\"]", q)
            if m: k='label'; pred=labels[m.group(1)]
            else: k='fixture:'+q[:30]
        if pred is None: st[k+'_na']+=1; continue
        ok=(pred==a); st[(k,ok)]+=1
        if not ok and len(ex[k])<4: ex[k].append((f.split('/')[-1], pred, a))
for k,v in sorted(st.items(), key=str): print(k, v)
for k,v in ex.items(): print(k, v)
