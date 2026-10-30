-- v46: nomes que existem. Especialidades e áreas com nome abreviado ou inventado passam a ter o nome oficial.
-- Só troca o NOME (nenhum arquivo, apostila, flashcard ou questão muda; nada é apagado).
-- Se já existir um tema com o nome novo no mesmo lugar, o antigo fica como está e aparece na lista do fim
-- (aí é só juntar os dois pelo Reorganizar). Pode rodar mais de uma vez.
do $$
declare
  n_esp int := 0; n_area int := 0; n_tema int := 0; r record; k int;
begin
  -- 1) especialidades
  for r in select * from (values
    ('Otorrino', 'Otorrinolaringologia'), ('Proctologia', 'Coloproctologia'),
    ('Infecto Bônus', 'Infectologia'), ('Cirurgia Bônus', 'Cirurgia')) as t(velho, novo)
  loop
    update materias m set periodo = r.novo
     where m.periodo = r.velho
       and not exists (select 1 from materias x where x.turma_id is not distinct from m.turma_id and x.acervo = m.acervo
                         and x.colecao = m.colecao and x.periodo = r.novo and x.disciplina = m.disciplina and x.materia = m.materia);
    get diagnostics k = row_count; n_esp := n_esp + k;
  end loop;
  -- 2) áreas (o tema com o mesmo nome da área também)
  for r in select * from (values
    ('Pólipos e CA Colorretal', 'Pólipos e Câncer Colorretal'), ('Nódulo Pulmonar e CA de Pulmão', 'Nódulo Pulmonar e Câncer de Pulmão'),
    ('Tumores do SNC', 'Tumores do Sistema Nervoso Central'), ('TOC', 'Transtorno Obsessivo-Compulsivo (TOC)'),
    ('TEPT e Transtornos Alimentares', 'Estresse Pós-Traumático e Transtornos Alimentares'),
    ('Oclusão Arterial Aguda de MMII', 'Oclusão Arterial Aguda dos Membros Inferiores'), ('Rouquidão e CA de Laringe', 'Rouquidão e Câncer de Laringe'),
    ('REMIT', 'Resposta Endócrino-Metabólica ao Trauma (REMIT)'), ('DPOC', 'Doença Pulmonar Obstrutiva Crônica (DPOC)'),
    ('TVP e TEP', 'Trombose Venosa Profunda e Tromboembolismo Pulmonar'), ('HIV/AIDS', 'HIV e AIDS'), ('CMV/HTLV', 'Citomegalovírus e HTLV'),
    ('ITU', 'Infecção do Trato Urinário (ITU)'), ('DRGE', 'Doença do Refluxo Gastroesofágico (DRGE)'),
    ('Doença de Crohn e RCU', 'Doença de Crohn e Retocolite Ulcerativa'), ('TRM e Coluna Vertebral', 'Trauma Raquimedular e Coluna Vertebral'),
    ('Profilaxia TEP/TVP', 'Profilaxia do Tromboembolismo Venoso'), ('Projeto ERAS/ACERTO', 'Recuperação Acelerada Pós-Operatória (ERAS e ACERTO)'),
    ('SOP', 'Síndrome dos Ovários Policísticos (SOP)'), ('DIP', 'Doença Inflamatória Pélvica (DIP)'), ('Rotina de USG', 'Ultrassonografia Obstétrica de Rotina'),
    ('RPMO', 'Ruptura Prematura das Membranas Ovulares (RPMO)'), ('Distúrbios Respiratórios do RN', 'Distúrbios Respiratórios do Recém-Nascido'),
    ('TEA e TDAH', 'Transtorno do Espectro Autista e TDAH'), ('FPIES', 'Enterocolite Induzida por Proteína Alimentar (FPIES)'),
    ('Outros Distúrbios TGI Funcionais', 'Outros Distúrbios Gastrointestinais Funcionais'), ('PCR na Infância', 'Parada Cardiorrespiratória na Infância'),
    ('HAS na Infância', 'Hipertensão Arterial na Infância'), ('Imuno/Dermatopediatria', 'Imunologia e Dermatologia Pediátrica'),
    ('SUS', 'Sistema Único de Saúde (SUS)'), ('Eczemas/Dermatites', 'Eczemas e Dermatites'), ('Hidrocele/Cistos de Cordão', 'Hidrocele e Cisto de Cordão')) as t(velho, novo)
  loop
    -- o tema que tem o mesmo nome da área muda junto com ela
    update materias m set disciplina = r.novo, materia = case when m.materia = r.velho then r.novo else m.materia end
     where m.disciplina = r.velho
       and not exists (select 1 from materias x where x.turma_id is not distinct from m.turma_id and x.acervo = m.acervo and x.colecao = m.colecao
                         and x.periodo = m.periodo and x.disciplina = r.novo and x.materia = case when m.materia = r.velho then r.novo else m.materia end);
    get diagnostics k = row_count; n_area := n_area + k;
    update materias m set materia = r.novo
     where m.materia = r.velho and m.disciplina <> r.velho
       and not exists (select 1 from materias x where x.turma_id is not distinct from m.turma_id and x.acervo = m.acervo and x.colecao = m.colecao
                         and x.periodo = m.periodo and x.disciplina = m.disciplina and x.materia = r.novo);
    get diagnostics k = row_count; n_tema := n_tema + k;
  end loop;
  -- 3) Citomegalovírus (de Infecto Bônus) entra junto de Citomegalovírus e HTLV
  update materias m set disciplina = 'Citomegalovírus e HTLV'
   where m.periodo = 'Infectologia' and m.disciplina = 'Citomegalovírus'
     and not exists (select 1 from materias x where x.turma_id is not distinct from m.turma_id and x.acervo = m.acervo and x.colecao = m.colecao
                       and x.periodo = 'Infectologia' and x.disciplina = 'Citomegalovírus e HTLV' and x.materia = m.materia);
  get diagnostics k = row_count; n_area := n_area + k;
  raise notice 'Especialidades renomeadas: %, áreas: %, temas: %', n_esp, n_area, n_tema;
end $$;

-- o que ficou com o nome antigo porque já existia um tema igual com o nome novo (junte pelo Reorganizar)
select acervo, colecao, periodo as especialidade, disciplina as area, materia as tema
  from materias
 where periodo in ('Otorrino', 'Proctologia', 'Infecto Bônus', 'Cirurgia Bônus')
    or disciplina in ('Pólipos e CA Colorretal', 'Nódulo Pulmonar e CA de Pulmão', 'Tumores do SNC', 'TOC', 'TEPT e Transtornos Alimentares',
                      'Oclusão Arterial Aguda de MMII', 'Rouquidão e CA de Laringe', 'REMIT', 'DPOC', 'TVP e TEP', 'HIV/AIDS', 'CMV/HTLV', 'ITU', 'DRGE',
                      'Doença de Crohn e RCU', 'TRM e Coluna Vertebral', 'Profilaxia TEP/TVP', 'Projeto ERAS/ACERTO', 'SOP', 'DIP', 'Rotina de USG', 'RPMO',
                      'Distúrbios Respiratórios do RN', 'TEA e TDAH', 'FPIES', 'Outros Distúrbios TGI Funcionais', 'PCR na Infância', 'HAS na Infância',
                      'Imuno/Dermatopediatria', 'SUS', 'Eczemas/Dermatites', 'Hidrocele/Cistos de Cordão')
 order by 3, 4, 5;
