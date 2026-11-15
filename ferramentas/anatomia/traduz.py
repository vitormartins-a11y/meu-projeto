# Tradução dos nomes do BodyParts3D (FMA, em inglês) para o português, por regras + dicionário.
# A ordem do inglês (modificadores antes do núcleo) vira a do português (núcleo e depois os adjetivos, concordando em gênero).
import re

# substantivos: palavra -> (português, gênero: m/f, plural: True/False)
N = {}
def n(gen, pl, **kw):
    for k, v in kw.items(): N[k.replace('_', '-')] = (v, gen, pl)
n('f', False, artery='artéria', arteria='artéria', vein='veia', part='parte', phalanx='falange', vertebra='vértebra', head='cabeça', tree='árvore',
  cartilage='cartilagem', rib='costela', tributary='tributária', valve='valva', gland='glândula', membrane='membrana', cusp='cúspide', plate='lâmina',
  eyelid='pálpebra', capsule='cápsula', cavity='cavidade', division='divisão', wall='parede', commissure='comissura', raphe='rafe', gingiva='gengiva',
  trochlea='tróclea', tibia='tíbia', cornea='córnea', ulna='ulna', chamber='câmara', iris='íris', leg='perna', clavicle='clavícula', maxilla='maxila',
  network='rede', insula='ínsula', retina='retina', patella='patela', concha='concha', matter='substância', scapula='escápula', vesicle='glândula',
  sclera='esclera', tongue='língua', ear='orelha', lamina='lâmina', cord='medula', epiglottis='epiglote', urethra='uretra', glans='glande',
  pons='ponte', gallbladder='vesícula biliar', prostate='próstata', trachea='traqueia', junction='junção', fossa='fossa', skin='pele',
  mandible='mandíbula', bladder='bexiga', linea='linha', stria='estria', taenia='tênia', habenula='habênula', amygdala='amígdala', corona='coroa',
  aorta='aorta', tooth_='dente', segment_='segmento', leaflet='válvula', hand='mão', parenchyma='parênquima', lobule='lóbulo',
  hemiazygos='hemiázigo', fibula='fíbula', azygos='ázigo', gingiva_='gengiva', aqueduct_='aqueduto', fornix_='fórnice', tract_='trato', lip_='lábio')
n('f', True, arteries='artérias', veins='veias', branches_='ramos')
n('m', False, branch='ramo', bone='osso', finger='dedo', nerve='nervo', gyrus='giro', foot='pé', tooth='dente', toe='dedo', set='conjunto', disk='disco',
  trunk='tronco', arch='arco', ligament='ligamento', lobe='lobo', ventricle='ventrículo', duct='ducto', muscle='músculo', segment='segmento', body='corpo',
  sulcus='sulco', tract='trato', colon='colo', atrium='átrio', brachium='braço', thumb='polegar', ganglion='gânglio', tendon='tendão', thalamus='tálamo',
  forebrain='prosencéfalo', hemisphere='hemisfério', jejunum='jejuno', ileum='íleo', humerus='úmero', femur='fêmur', thymus='timo', sac='saco',
  forearm='antebraço', lake='lago', canaliculus='canalículo', liver='fígado', testis='testículo', calcaneus='calcâneo', eyeball='bulbo do olho', hip='quadril',
  midbrain='mesencéfalo', pancreas='pâncreas', hair='cabelo', limb='membro', axis='áxis', talus='tálus', kidney='rim', epididymis='epidídimo', nucleus='núcleo',
  ureter='ureter', hippocampus='hipocampo', wrist='punho', bronchus='brônquio', radius='rádio', esophagus='esôfago', duodenum='duodeno', diaphragm='diafragma',
  mesoappendix='mesoapêndice', process='processo', plexus='plexo', tuber='túber', chiasm='quiasma', canal='canal', peduncle='pedúnculo', appendix='apêndice',
  aqueduct='aqueduto', stomach='estômago', sternum='esterno', vomer='vômer', spleen='baço', rectum='reto', sacrum='sacro', sphincter='esfíncter',
  hypothalamus='hipotálamo', mesentery='mesentério', intestine='intestino', foramen='forame', cerebellum='cerebelo', septum='septo',
  telencephalon='telencéfalo', eyebrow='supercílio', sinus='seio', manubrium='manúbrio', tentorium='tentório', atlas='atlas', lip='lábio',
  mesocolon='mesocolo', corpus='corpo', putamen='putame', fornix='fórnice', colliculus='colículo', conus='cone', globus='globo', hallux='hálux',
  scaphoid='escafoide', lunate='semilunar', triquetral='piramidal', pisiform='pisiforme', trapezium='trapézio', trapezoid='trapezoide',
  capitate='capitato', hamate='hamato', cuboid='cuboide', navicular='navicular', jaw='maxilar', uterus='útero', ovary='ovário', heart='coração',
  lung='pulmão', larynx='laringe', pharynx='faringe', brain='encéfalo', cerebrum='cérebro', skull='crânio', pelvis='pelve', coccyx='cóccix',
  precuneus='pré-cuneus', lens='cristalino', penis='pênis', retinaculum='retináculo', cuneus='cúneus', claustrum='claustro', vermis='verme', cecum='ceco', pylorus='piloro', omentum='omento')
n('m', True, branches='ramos', lumbricals='lumbricais', interossei='interósseos', levatores='levantadores', intertransversarii='intertransversários',
  interspinales='interespinais', rotatores='rotadores', teeth='dentes')

# núcleos latinos dos músculos (vêm na frente no nome em latim: "flexor pollicis longus")
LH = {'flexor': 'flexor', 'extensor': 'extensor', 'abductor': 'abdutor', 'adductor': 'adutor', 'opponens': 'oponente', 'pronator': 'pronador',
      'tensor': 'tensor', 'levator': 'levantador', 'biceps': 'bíceps', 'triceps': 'tríceps', 'vastus': 'vasto', 'tibialis': 'tibial',
      'fibularis': 'fibular', 'palmaris': 'palmar', 'obturator': 'obturador', 'gemellus': 'gêmeo', 'quadratus': 'quadrado', 'rectus': 'reto',
      'obliquus': 'oblíquo', 'transversus': 'transverso', 'serratus': 'serrátil', 'pectoralis': 'peitoral', 'gluteus': 'glúteo', 'splenius': 'esplênio',
      'longissimus': 'longuíssimo', 'iliocostalis': 'iliocostal', 'spinalis': 'espinal', 'semispinalis': 'semiespinal', 'scalenus': 'escaleno',
      'constrictor': 'constritor', 'rotator': 'rotador', 'teres': 'redondo', 'psoas': 'psoas', 'deltoid': 'deltoide', 'trapezius': 'trapézio',
      'rhomboid': 'romboide', 'platysma': 'platisma', 'sartorius': 'sartório', 'gracilis': 'grácil', 'soleus': 'sóleo', 'gastrocnemius': 'gastrocnêmio',
      'piriformis': 'piriforme', 'popliteus': 'poplíteo', 'iliacus': 'ilíaco', 'pectineus': 'pectíneo', 'plantaris': 'plantar', 'subclavius': 'subclávio',
      'supraspinatus': 'supraespinal', 'infraspinatus': 'infraespinal', 'subscapularis': 'subescapular', 'brachialis': 'braquial',
      'brachioradialis': 'braquiorradial', 'coracobrachialis': 'coracobraquial', 'anconeus': 'ancôneo', 'supinator': 'supinador', 'digastric': 'digástrico',
      'mylohyoid': 'milo-hióideo', 'geniohyoid': 'genio-hióideo', 'stylohyoid': 'estilo-hióideo', 'omohyoid': 'omo-hióideo', 'sternohyoid': 'esterno-hióideo',
      'sternothyroid': 'esternotireóideo', 'thyrohyoid': 'tíreo-hióideo', 'sternocleidomastoid': 'esternocleidomastóideo', 'genioglossus': 'genioglosso',
      'hyoglossus': 'hioglosso', 'vocalis': 'vocal', 'semimembranosus': 'semimembranáceo', 'semitendinosus': 'semitendíneo', 'puborectalis': 'puborretal',
      'pubococcygeus': 'pubococcígeo', 'iliococcygeus': 'iliococcígeo', 'coccygeus': 'coccígeo', 'aryepiglotticus': 'ariepiglótico',
      'palatopharyngeus': 'palatofaríngeo', 'salpingopharyngeus': 'salpingofaríngeo', 'stylopharyngeus': 'estilofaríngeo', 'cricothyroid': 'cricotireóideo',
      'crico-arytenoid': 'cricoaritenóideo', 'thyro-arytenoid': 'tireoaritenóideo', 'interspinalis': 'interespinal', 'intertransversarius': 'intertransversário',
      'iliopsoas': 'iliopsoas', 'masseter': 'masseter', 'buccinator': 'bucinador', 'orbicularis': 'orbicular', 'risorius': 'risório', 'procerus': 'prócero',
      'mentalis': 'mentual', 'nasalis': 'nasal', 'depressor': 'abaixador', 'corrugator': 'corrugador', 'zygomaticus': 'zigomático', 'temporalis': 'temporal',
      'pterygoid': 'pterigóideo', 'multifidus': 'multífido', 'latissimus': 'latíssimo', 'arytenoid': 'aritenóideo', 'uvular': 'da úvula'}
# genitivos latinos (vão para o fim) e expressões
G = {'pollicis': 'do polegar', 'hallucis': 'do hálux', 'capitis': 'da cabeça', 'cervicis': 'do pescoço', 'thoracis': 'do tórax', 'lumborum': 'do lombo',
     'digiti minimi': 'do dedo mínimo', 'carpi': 'do carpo', 'digitorum': 'dos dedos', 'indicis': 'do indicador', 'colli': 'do pescoço',
     'palpebrae superioris': 'da pálpebra superior', 'scapulae': 'da escápula', 'veli palatini': 'do véu palatino', 'fasciae latae': 'da fáscia lata',
     'ani': 'do ânus', 'costarum': 'das costelas', 'cerebelli': 'do cerebelo', 'dorsi': 'do dorso', 'oris': 'da boca', 'oculi': 'do olho', 'labii': 'do lábio',
     'anguli': 'do ângulo', 'nasi': 'do nariz', 'pedis': 'do pé', 'cruris': 'da perna', 'uvulae': 'da úvula', 'linguae': 'da língua', 'tympani': 'do tímpano'}
# adjetivos (forma masculina singular) e latinos
A = {'left': 'esquerdo', 'right': 'direito', 'anterior': 'anterior', 'posterior': 'posterior', 'segmental': 'segmentar', 'superior': 'superior',
     'lateral': 'lateral', 'inferior': 'inferior', 'middle': 'médio', 'medial': 'medial', 'hepatic': 'hepático', 'palmar': 'palmar', 'digital': 'digital',
     'thoracic': 'torácico', 'cerebral': 'cerebral', 'secondary': 'permanente', 'basal': 'basal', 'plantar': 'plantar', 'dorsal': 'dorsal',
     'temporal': 'temporal', 'intervertebral': 'intervertebral', 'distal': 'distal', 'bronchial': 'brônquico', 'common': 'comum', 'proximal': 'proximal',
     'cervical': 'cervical', 'lumbar': 'lombar', 'circumflex': 'circunflexo', 'internal': 'interno', 'upper': 'superior', 'ulnar': 'ulnar', 'renal': 'renal',
     'oblique': 'oblíquo', 'superficial': 'superficial', 'deep': 'profundo', 'lower': 'inferior', 'portal': 'porta', 'little': 'mínimo',
     'metacarpal': 'metacarpal', 'interosseous': 'interósseo', 'major': 'maior', 'genicular': 'genicular', 'costal': 'costal', 'coronary': 'coronário',
     'femoral': 'femoral', 'ring': 'anular', 'occipital': 'occipital', 'iliac': 'ilíaco', 'lacrimal': 'lacrimal', 'epigastric': 'epigástrico',
     'metatarsal': 'metatarsal', 'apical': 'apical', 'tibial': 'tibial', 'venous': 'venoso', 'transverse': 'transverso', 'interventricular': 'interventricular',
     'descending': 'descendente', 'cerebellar': 'cerebelar', 'radial': 'radial', 'central': 'central', 'index': 'indicador', 'recurrent': 'recorrente',
     'long': 'longo', 'humeral': 'umeral', 'brachial': 'braquial', 'pulmonary': 'pulmonar', 'external': 'externo', 'ascending': 'ascendente', 'colic': 'cólico',
     'frontal': 'frontal', 'caudate': 'caudado', 'parietal': 'parietal', 'incisor': 'incisivo', 'minor': 'menor', 'premolar': 'pré-molar', 'molar': 'molar',
     'thoraco-acromial': 'toracoacromial', 'callosomarginal': 'calosomarginal', 'cuneiform': 'cuneiforme', 'deltoid': 'deltoide', 'lumbrical': 'lumbrical',
     'hepatovenous': 'hepatovenoso', 'collateral': 'colateral', 'median': 'mediano', 'optic': 'óptico', 'ciliary': 'ciliar', 'communicating': 'comunicante',
     'nasal': 'nasal', 'thyrohyoid': 'tíreo-hióideo', 'pharyngeal': 'faríngeo', 'tarsal': 'tarsal', 'lingular': 'lingular',
     'pancreaticoduodenal': 'pancreaticoduodenal', 'suprarenal': 'suprarrenal', 'scapular': 'escapular', 'septal': 'septal', 'pancreatic': 'pancreático',
     'choroidal': 'corióideo', 'marginal': 'marginal', 'spinal': 'espinal', 'papillary': 'papilar', 'mesenteric': 'mesentérico', 'short': 'curto',
     'carpal': 'carpal', 'carotid': 'carótida', 'ileocolic': 'ileocólico', 'angular': 'angular', 'posteromedial': 'posteromedial', 'precentral': 'pré-central',
     'testicular': 'testicular', 'gluteal': 'glúteo', 'geniculate': 'geniculado', 'ethmoidal': 'etmoidal', 'axillary': 'axilar', 'subclavian': 'subclávio',
     'phrenic': 'frênico', 'pontine': 'pontino', 'postcentral': 'pós-central', 'cardiac': 'cardíaco', 'popliteal': 'poplíteo', 'small': 'delgado',
     'intermediate': 'intermédio', 'pericallosal': 'pericaloso', 'clavicular': 'clavicular', 'subcostal': 'subcostal', 'ophthalmic': 'oftálmico',
     'thoracodorsal': 'toracodorsal', 'great': 'magno', 'saphenous': 'safeno', 'suprascapular': 'supraescapular', 'acromial': 'acromial', 'gastric': 'gástrico',
     'nasociliary': 'nasociliar', 'oculomotor': 'oculomotor', 'subscapular': 'subescapular', 'musculophrenic': 'musculofrênico', 'sacral': 'sacral',
     'brachiocephalic': 'braquiocefálico', 'thyroid': 'tireóideo', 'abdominal': 'abdominal', 'terminal': 'terminal', 'calcaneal': 'calcâneo',
     'tricuspid': 'tricúspide', 'choroid': 'corioide', 'perforating': 'perfurante', 'anterolateral': 'anterolateral', 'tendinous': 'tendíneo', 'ileal': 'ileal',
     'sphenoid': 'esfenoide', 'aortic': 'aórtico', 'accessory': 'acessório', 'pudendal': 'pudendo', 'supra-orbital': 'supraorbital',
     'supratrochlear': 'supratroclear', 'temporo-occipital': 'temporo-occipital', 'mitral': 'mitral', 'thalamogeniculate': 'talamogeniculado',
     'infratrochlear': 'infratroclear', 'deferent': 'deferente', 'fusiform': 'fusiforme', 'iliotibial': 'iliotibial', 'pectoral': 'peitoral',
     'parahippocampal': 'para-hipocampal', 'sigmoid': 'sigmoide', 'splenial': 'esplenial', 'paracentral': 'paracentral', 'supramarginal': 'supramarginal',
     'cephalic': 'cefálico', 'ureteric': 'uretérico', 'postcommunicating': 'pós-comunicante', 'splenic': 'esplênico', 'trochlear': 'troclear',
     'intermediomedial': 'intermediomedial', 'sublingual': 'sublingual', 'precuneal': 'pré-cuneal', 'cecal': 'cecal', 'hypothalamic': 'hipotalâmico',
     'pterygomandibular': 'pterigomandibular', 'insular': 'insular', 'thalamoperforating': 'talamoperfurante', 'antebrachial': 'antebraquial',
     'basilic': 'basílico', 'precommunicating': 'pré-comunicante', 'jugular': 'jugular', 'zygomatic': 'zigomático', 'ventricular': 'ventricular',
     'rectal': 'retal', 'gastroepiploic': 'gastromental', 'gastro-epiploic': 'gastromental', 'straight': 'reto', 'suspensory': 'suspensor',
     'arterial': 'arterial', 'palatine': 'palatino', 'vocal': 'vocal', 'submandibular': 'submandibular', 'adrenal': 'suprarrenal', 'vertebral': 'vertebral',
     'vermian': 'vermiano', 'iliolumbar': 'iliolombar', 'thyrocervical': 'tireocervical', 'corniculate': 'corniculado', 'white': 'branco',
     'costocervical': 'costocervical', 'alar': 'alar', 'arcuate': 'arqueado', 'sesamoid': 'sesamoide', 'sternocostal': 'esternocostal',
     'nasolacrimal': 'nasolacrimal', 'cubital': 'cubital', 'main': 'principal', 'prefrontal': 'pré-frontal', 'seminal': 'seminal', 'polar': 'polar',
     'celiac': 'celíaco', 'cingulate': 'cingulado', 'esophageal': 'esofágico', 'oesophageal': 'esofágico', 'pineal': 'pineal', 'orbital': 'orbital',
     'urinary': 'urinário', 'pre-hepatic': 'pré-hepático', 'diagonal': 'diagonal', 'gastroduodenal': 'gastroduodenal', 'mammillary': 'mamilar',
     'hyo-epiglottic': 'hioepiglótico', 'thyro-epiglottic': 'tireoepiglótico', 'caudal': 'caudal', 'pubic': 'púbico', 'appendicular': 'apendicular',
     'laterobasal': 'laterobasal', 'ileocecal': 'ileocecal', 'lobar': 'lobar', 'ethmoid': 'etmoide', 'interpeduncular': 'interpeduncular',
     'mediobasal': 'mediobasal', 'basilar': 'basilar', 'subsuperior': 'subsuperior', 'innermost': 'íntimo', 'frontobasal': 'frontobasal',
     'cricothyroid': 'cricotireóideo', 'crico-arytenoid': 'cricoaritenóideo', 'thyro-arytenoid': 'tireoaritenóideo', 'arytenoid': 'aritenóideo',
     'cystic': 'cístico', 'check': 'de contenção', 'proper': 'próprio', 'biliary': 'biliar', 'hyoid': 'hioide', 'cricoid': 'cricóideo', 'vitreous': 'vítreo',
     'intercostal': 'intercostal', 'digital_': 'digital', 'lingual': 'lingual', 'facial': 'facial', 'maxillary': 'maxilar', 'mental': 'mentual',
     'buccal': 'bucal', 'labial': 'labial', 'auricular': 'auricular', 'parotid': 'parotídeo', 'vesical': 'vesical', 'uterine': 'uterino', 'ovarian': 'ovárico',
     'obturator': 'obturatório', 'gonadal': 'gonadal', 'inguinal': 'inguinal', 'pericardial': 'pericárdico', 'pleural': 'pleural', 'tracheal': 'traqueal',
     'laryngeal': 'laríngeo', 'thymic': 'tímico', 'mediastinal': 'mediastinal', 'vagal': 'vagal', 'hypoglossal': 'hipoglosso', 'glossopharyngeal': 'glossofaríngeo',
     'trigeminal': 'trigêmeo', 'abducent': 'abducente', 'olfactory': 'olfatório', 'vestibulocochlear': 'vestibulococlear', 'cochlear': 'coclear',
     'gray': 'cinzento', 'grey': 'cinzento', 'lentiform': 'lentiforme', 'red': 'rubro', 'black': 'negro', 'dentate': 'denteado', 'olivary': 'olivar',
     'striate': 'estriado', 'calcarine': 'calcarino', 'lingual_': 'lingual', 'angular_': 'angular', 'orbitofrontal': 'orbitofrontal', 'opercular': 'opercular',
     'triangular': 'triangular', 'rolandic': 'rolândico', 'prerolandic': 'pré-rolândico', 'thalamic': 'talâmico', 'lenticulostriate': 'lenticuloestriado',
     'striate_': 'estriado', 'hippocampal': 'hipocampal', 'uncal': 'uncal', 'thalamostriate': 'talamoestriado', 'medullary': 'medular', 'lumbosacral': 'lombossacral',
     'sural': 'sural', 'fibular': 'fibular', 'peroneal': 'fibular', 'malleolar': 'maleolar', 'tarsal_': 'tarsal', 'navicular': 'navicular', 'cuboid': 'cuboide',
     'patellar': 'patelar', 'scrotal': 'escrotal', 'penile': 'peniano', 'dorsal_': 'dorsal', 'umbilical': 'umbilical', 'renal_': 'renal', 'interlobar': 'interlobar',
     'gastro-omental': 'gastromental', 'omental': 'omental', 'duodenal': 'duodenal', 'jejunal': 'jejunal', 'sigmoidal': 'sigmóideo', 'hemorrhoidal': 'retal',
     'vertebral_': 'vertebral', 'radicular': 'radicular', 'segmental_': 'segmentar', 'sacral_': 'sacral', 'coccygeal': 'coccígeo', 'spinous': 'espinhoso', 'anal': 'anal', 'canine': 'canino', 'vertical': 'vertical',
     # latinos
     'longus': 'longo', 'brevis': 'curto', 'magnus': 'magno', 'maximus': 'máximo', 'medius': 'médio', 'minimus': 'mínimo', 'teres': 'redondo',
     'quadratus': 'quadrado', 'profundus': 'profundo', 'superficialis': 'superficial', 'radialis': 'radial', 'ulnaris': 'ulnar', 'internus': 'interno',
     'externus': 'externo', 'lateralis': 'lateral', 'medialis': 'medial', 'intermedius': 'intermédio', 'tertius': 'terceiro', 'obliquus': 'oblíquo',
     'rectus': 'reto', 'transversus': 'transverso', 'accessorius': 'acessório', 'princeps': 'principal', 'breves': 'curtos', 'longi': 'longos',
     'femoris': 'femoral', 'brachii': 'braquial', 'anterior_': 'anterior', 'callosum': 'caloso', 'cavernosum': 'cavernoso', 'spongiosum': 'esponjoso',
     'pallidus': 'pálido', 'alba': 'alba', 'cinereum': 'cinéreo', 'elasticus': 'elástico', 'terminalis': 'terminal', 'ciliaris': 'ciliar',
     'oblongata': '', 'libera': 'livre', 'mesocolica': 'mesocólica', 'omentalis': 'omental', 'dorsalis': 'dorsal', 'medullaris': 'medular',
     'ii': 'II', 'iii': 'III', 'iv': 'IV', 'v': 'V', 'vi': 'VI', 'vii': 'VII', 'viii': 'VIII', 'ix': 'IX', 'x': 'X', 'xi': 'XI', 'xii': 'XII'}
A = {k.rstrip('_'): v for k, v in A.items()}
ORD = {'first': 'primeiro', 'second': 'segundo', 'third': 'terceiro', 'fourth': 'quarto', 'fifth': 'quinto', 'sixth': 'sexto', 'seventh': 'sétimo',
       'eighth': 'oitavo', 'ninth': 'nono', 'tenth': 'décimo', 'eleventh': 'décimo primeiro', 'twelfth': 'décimo segundo'}
# expressões de mais de uma palavra (trocadas antes de separar)
FRASES = [('big toe', 'hallux'), ('upper jaw', '@maxila'), ('lower jaw', '@mandibula'), ('vena cava', '@veiacava'), ('medulla oblongata', '@bulbo'),
          ('pubic hair', '@pelospubicos'), ('hair of head', '@cabelo'), ('urinary bladder', '@bexiga'), ('pituitary gland', '@hipofise'),
          ('pineal body', '@pineal'), ('thyroid gland', '@tireoide'), ('xiphoid process', '@xifoide'), ('mammillary body', '@mamilar'),
          ('small intestine', '@delgado'), ('choroid plexus', '@plexocorioide'), ('optic chiasm', '@quiasma'), ('external ear', '@orelhaext'),
          ('corpus callosum', '@caloso'), ('linea alba', '@lineaalba'), ('tuber cinereum', '@tuber'), ('globus pallidus', '@globo'),
          ('stria terminalis', '@estria'), ('conus elasticus', '@cone'), ('corona ciliaris', '@coroa'), ('tentorium cerebelli', '@tenda'),
          ('cerebral aqueduct', '@aqueduto'), ('white matter', '@substbranca'), ('ventricular system', '@sistventr')]
ESP = {'@maxila': ('maxila', 'f', False), '@mandibula': ('mandíbula', 'f', False), '@veiacava': ('veia cava', 'f', False), '@bulbo': ('bulbo', 'm', False),
       '@pelospubicos': ('pelos pubianos', 'm', True), '@cabelo': ('cabelo', 'm', False), '@bexiga': ('bexiga urinária', 'f', False),
       '@hipofise': ('hipófise', 'f', False), '@pineal': ('glândula pineal', 'f', False), '@tireoide': ('glândula tireoide', 'f', False),
       '@xifoide': ('processo xifoide', 'm', False), '@mamilar': ('corpo mamilar', 'm', False), '@delgado': ('intestino delgado', 'm', False),
       '@plexocorioide': ('plexo corióideo', 'm', False), '@quiasma': ('quiasma óptico', 'm', False), '@orelhaext': ('orelha externa', 'f', False),
       '@caloso': ('corpo caloso', 'm', False), '@lineaalba': ('linha alba', 'f', False), '@tuber': ('túber cinéreo', 'm', False),
       '@globo': ('globo pálido', 'm', False), '@estria': ('estria terminal', 'f', False), '@cone': ('cone elástico', 'm', False),
       '@coroa': ('coroa ciliar', 'f', False), '@tenda': ('tenda do cerebelo', 'f', False), '@aqueduto': ('aqueduto do mesencéfalo', 'm', False),
       '@substbranca': ('substância branca', 'f', False), '@sistventr': ('sistema ventricular', 'm', False)}
NAO = set()


def flex(adj, gen, pl):
    """concorda o adjetivo (dado no masculino singular) com o núcleo"""
    if not adj or adj.startswith('de ') or adj.startswith('da ') or adj.startswith('do ') or adj in ('porta', 'carótida', 'alba') or adj.isupper(): return adj
    w = adj.split(' ')
    def um(x):
        if gen == 'f':
            if x.endswith('o') and x not in ('pré-molar',): x = x[:-1] + 'a'
            elif x.endswith('ês'): x = x[:-2] + 'esa'
        if pl:
            if x.endswith('al'): x = x[:-2] + 'ais'
            elif x.endswith('ar') or x.endswith('or') or x.endswith('er'): x = x + 'es'
            elif x.endswith('m'): x = x[:-1] + 'ns'
            elif not x.endswith('s'): x = x + 's'
        return x
    return ' '.join(um(x) for x in w)


def artigo(gen, pl, prep='de'):
    a = {('m', False): 'o', ('f', False): 'a', ('m', True): 'os', ('f', True): 'as'}[(gen, pl)]
    if prep == 'de': return 'd' + a
    if prep == 'com': return 'com ' + a
    if prep == 'para': return 'para ' + ({'o': 'o', 'a': 'a', 'os': 'os', 'as': 'as'}[a])
    return a


def segmento(txt):
    """traduz um pedaço sem "of": devolve (texto, gênero, plural)"""
    for a, b in FRASES: txt = re.sub(r'\b' + a + r'\b', b, txt)
    gens = []
    for k in sorted(G, key=len, reverse=True):
        if re.search(r'\b' + k + r'\b', txt): gens.append(G[k]); txt = re.sub(r'\b' + k + r'\b', ' ', txt)
    toks = txt.split(); lado = None
    if 'left' in toks: lado = 'esquerdo'; toks.remove('left')
    if 'right' in toks: lado = 'direito'; toks.remove('right')
    ords = [t for t in toks if t in ORD]; toks = [t for t in toks if t not in ORD]
    if not toks: toks = ['?']
    # o núcleo: um substantivo (o último), um núcleo latino de músculo na frente, ou a última palavra
    hi = None
    for i in range(len(toks) - 1, -1, -1):
        if toks[i] in N or toks[i] in ESP: hi = i; break
    if hi is None and toks[0] in LH: hi = 0
    if hi is None:
        for i in range(len(toks) - 1, -1, -1):
            if toks[i] in LH: hi = i; break
    if hi is None: hi = len(toks) - 1
    h = toks[hi]
    if h in ESP: nucleo, gen, pl = ESP[h]
    elif h in N: nucleo, gen, pl = N[h]
    elif h in LH: nucleo, gen, pl = LH[h], 'm', False
    elif h in A: nucleo, gen, pl = A[h], 'm', False
    else: nucleo, gen, pl = h, 'm', False; NAO.add(h)
    # um substantivo antes do núcleo ("caudate lobe branch") vira complemento: "ramo do lobo caudado"
    j = next((i for i in range(hi - 1, -1, -1) if toks[i] in N or toks[i] in ESP), None)
    if j is not None:
        t2, g2, p2 = segmento(' '.join(toks[:j + 1])); gens.insert(0, artigo(g2, p2) + ' ' + t2); toks = toks[j + 1:]; hi -= j + 1
    antes = toks[:hi][::-1]; depois = toks[hi + 1:]
    mods = []
    for t in antes + depois:
        if t in A: mods.append(flex(A[t], gen, pl))
        elif t in LH: mods.append(flex(LH[t], gen, pl))
        elif t in ESP: mods.append(ESP[t][0])
        elif t in N: mods.append(N[t][0])
        else: mods.append(t); NAO.add(t)
    o = [flex(ORD[x], gen, pl) for x in ords] + [nucleo] + [m for m in mods if m] + gens + ([flex(lado, gen, pl)] if lado else [])
    return ' '.join(o), gen, pl


def traduz(nome):
    s = nome.strip().lower()
    if not s: return ''
    s = re.sub(r'^set of ', '', s)
    s = s.replace('head of muscle', 'head')
    partes = re.split(r' (of|with|to) ', s)
    segs = [partes[0]]; preps = []
    for i in range(1, len(partes), 2): preps.append(partes[i]); segs.append(partes[i + 1])
    out, g0, p0 = segmento(segs[0])
    for prep, sg in zip(preps, segs[1:]):
        t, g, p = segmento(sg)
        out += ' ' + artigo(g, p, {'of': 'de', 'with': 'com', 'to': 'para'}[prep]) + ' ' + t
    out = re.sub(r'\s+', ' ', out).strip()
    return out[:1].upper() + out[1:]


if __name__ == '__main__':
    import json, sys, random
    nomes = sorted(set(v[1] for v in json.load(open(sys.argv[1])).values() if v[1]))
    random.seed(int(sys.argv[2]) if len(sys.argv) > 2 else 3)
    for x in random.sample(nomes, 70): print(f'{x}  ->  {traduz(x)}')
    for x in nomes: traduz(x)
    print('NÃO TRADUZIDAS:', sorted(NAO))
