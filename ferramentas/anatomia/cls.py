import json,sys,re,collections
B=sys.argv[1]; A=json.load(open(B+'/../isa_anc.json'))
def cls(n,a):
    a=set(a); s=' | '.join([n]+sorted(a)).lower(); n=n.lower()
    if re.search(r'\bskin\b|integument',n): return 'pele'
    if re.search(r'papillary muscle',n): return 'cardiovascular'
    if re.search(r'xiphoid|interosseous membrane',n): return 'esqueleto'
    if re.search(r'interventricular foramen|interpeduncular',n): return 'nervoso'
    if re.search(r'trapezius|interossei|lumbricals|intertransversari|interspinales|levatores|intercostal muscle|rotator\b|raphe',n): return 'musculos'
    if re.search(r'muscle organ|zone of muscle|head of muscle|tendon|aponeuros|fascia|retinacul|iliotibial|linea alba|tendinous|sphincter|\bmuscle\b|diaphragm',s) and not re.search(r'heart|cardiac|ventric|atri',n): return 'musculos'
    if re.search(r'bone organ|cartilage|\bbone\b|tooth|teeth|phalanx|vertebra|sacrum|coccyx|ligament|joint|meniscus|intervertebral|disc\b|skull|mandible|maxilla|rib\b|sternum|patella|femur|tibia|fibula|humerus|radius|ulna|scapula|clavicle|hyoid|ossicle|carpal|tarsal',s) and not re.search(r'arter|vein|nerve',n): return 'esqueleto'
    if re.search(r'arter|\bvein|venous|vena|aorta|heart|cardiac|coronary|atrium|ventricle of heart|valve|sinus of dura|dural venous|vascular|capillar|mitral|tricuspid|pulmonary trunk',s) and not re.search(r'nerve|lymph',n): return 'cardiovascular'
    if re.search(r'nerve|neural|neur|brain|gyrus|sulcus|ganglion|spinal cord|cerebr|cerebell|thalam|hippocamp|callosum|fornix|nucleus|colliculus|geniculate|pons|medulla oblongata|midbrain|lobe of cerebral|globus pallidus|putamen|caudate|amygdal|insula|chiasm|retina|eyeball|lens|cornea|iris|sclera|choroid|vitreous|ventricular system|lateral ventricle|third ventricle|fourth ventricle|optic|cochlea|vestibul|semicircular|tympan|auditory|ear\b|chamber of|pituitary|pineal',s): return 'nervoso'
    return 'orgaos'
for k,v in A.items():
    if not v[1] and k+'M' in A: v[1]=A[k+'M'][1]; v[2]=A[k+'M'][2]
    if not v[1] and k.endswith('M') and k[:-1] in A: v[1]=A[k[:-1]][1]; v[2]=A[k[:-1]][2]
json.dump(A,open(B+'/../isa_anc2.json','w'))
c=collections.Counter(); ex=collections.defaultdict(list)
for k,(cid,n,a) in A.items():
    t=cls(n or '',a); c[t]+=1; ex[t].append(n)
print(c)
for t in ex:
    import random; random.seed(1); print('==',t, sorted(set(ex[t])) if t=='orgaos' else '')
json.dump({k:cls(v[1] or '',v[2]) for k,v in A.items()},open(B+'/../sist.json','w'))
