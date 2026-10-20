-- v38: cada página fica no tema do arquivo dela.
-- Mudanças antigas de lugar deixaram páginas marcadas com um tema enquanto o arquivo delas já estava em outro. A apostila
-- desses temas misturava assuntos de outros arquivos (ex.: Coluna com Quedas no idoso, Escoliose, Sífilis congênita).
-- Pode rodar mais de uma vez.

-- 1) os temas envolvidos (o que tinha a página a mais e o que estava sem ela) têm a apostila refeita pela fila da IA
with erradas as (
  select distinct p.materia_id as velho, d.materia_id as novo
  from paginas p join documentos d on d.id = p.documento_id
  where p.materia_id is distinct from d.materia_id)
update resumos r set dados = jsonb_set(r.dados, '{docs}', '[]'::jsonb)
where r.dados ->> 'versao' = '4'
  and r.materia_id in (select velho from erradas union select novo from erradas);

-- 2) cada página volta para o tema do arquivo dela
update paginas p set materia_id = d.materia_id
from documentos d
where d.id = p.documento_id and p.materia_id is distinct from d.materia_id;

-- 3) daqui em diante: a página nova (ou mudada) fica no tema do arquivo; o arquivo que muda de tema leva as páginas
create or replace function paginas_seguem_arquivo() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  new.materia_id := coalesce((select d.materia_id from documentos d where d.id = new.documento_id), new.materia_id);
  return new;
end $$;
drop trigger if exists paginas_seguem_arquivo on paginas;
create trigger paginas_seguem_arquivo before insert or update of documento_id, materia_id on paginas
  for each row execute function paginas_seguem_arquivo();

create or replace function arquivo_leva_paginas() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  update paginas set materia_id = new.materia_id where documento_id = new.id and materia_id is distinct from new.materia_id;
  return null;
end $$;
drop trigger if exists arquivo_leva_paginas on documentos;
create trigger arquivo_leva_paginas after update of materia_id on documentos
  for each row when (old.materia_id is distinct from new.materia_id) execute function arquivo_leva_paginas();

-- quantos temas vão ser refeitos (para conferir)
select count(*) as temas_para_refazer from resumos where dados ->> 'versao' = '4' and dados -> 'docs' = '[]'::jsonb;
