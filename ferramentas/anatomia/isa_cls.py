import collections, os, re, sys, json
B=sys.argv[1]
rel=[l.rstrip('\n').split('\t') for l in open(B+'/isa_inclusion_relation_list.txt')][1:]
nome={}; pais=collections.defaultdict(set)
for p,pn,c,cn in rel: nome[p]=pn; nome[c]=cn; pais[c].add(p)
fjconc={}
for l in list(open(B+'/isa_element_parts.txt'))[1:]:
    cid,nm,fj=l.rstrip('\n').split('\t'); nome.setdefault(cid,nm)
D=B+'/isa_BP3D_4.0_obj_99'
fj={}
for f in os.listdir(D):
    c=n=None
    for l in open(D+'/'+f,errors='ignore'):
        if l.startswith('# Concept ID'): c=l.split(':',1)[1].strip()
        if l.startswith('# English name'): n=l.split(':',1)[1].strip()
        if l.startswith('v '): break
    fj[f[:-4]]=(c,n)
def anc(c):
    s=set(); st=[c]
    while st:
        x=st.pop()
        for p in pais.get(x,()):
            if p not in s: s.add(p); st.append(p)
    return s
cnt=collections.Counter()
for k,(c,n) in fj.items():
    for a in anc(c): cnt[nome.get(a,a)]+=1
json.dump({k:[c,n,sorted(nome.get(a,a) for a in anc(c))] for k,(c,n) in fj.items()},open(B+'/../isa_anc.json','w'))
for nm,v in cnt.most_common(80): print(v,nm)
