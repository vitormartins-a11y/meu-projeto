-- v47: arquivos grandes só para consulta e refazer o acervo no modelo novo.
-- 1) Cada arquivo pode ser marcado "Usar na apostila" ou "Só consulta" (sem marca, o app decide pelo tamanho: mais de
--    150 páginas fica só para consulta). Nada é apagado: o arquivo continua no tema para ler e pesquisar.
-- 2) Uma coluna pequena com o modelo da apostila de cada tema: a fila sabe o que já foi refeito no modelo novo sem baixar
--    o tema inteiro (pode demorar um pouco na primeira vez, enquanto o banco preenche a coluna).
-- 3) A lista dos arquivos grandes para a Administração (só o administrador).
-- 4) O robô guarda a apostila anterior de cada tema refeito como uma versão do tema, sem o limite de 5 por dia.
-- Pode rodar mais de uma vez.
alter table documentos add column if not exists uso_ia text;
do $$ begin
  if not exists (select 1 from pg_constraint where conname = 'documentos_uso_ia_ok') then
    alter table documentos add constraint documentos_uso_ia_ok check (uso_ia is null or uso_ia in ('usar', 'consulta'));
  end if;
end $$;

alter table resumos add column if not exists st_modelo text generated always as (dados->>'modelo') stored;

create index if not exists paginas_documento on paginas (documento_id);
create or replace function docs_grandes(min_paginas int default 150)
returns table (id uuid, materia_id uuid, nome text, tipo text, paginas bigint, uso_ia text)
language plpgsql stable security definer set search_path = public as $$
begin
  if not (eh_admin() or coalesce(auth.role(), '') = 'service_role') then raise exception 'Só o administrador.'; end if;
  return query
    select d.id, d.materia_id, d.nome, d.tipo, count(p.id) as paginas, d.uso_ia
      from documentos d left join paginas p on p.documento_id = d.id
     group by d.id
    having count(p.id) > min_paginas or d.uso_ia is not null
     order by count(p.id) desc
     limit 2000;
end $$;
revoke all on function docs_grandes(int) from public, anon;
grant execute on function docs_grandes(int) to authenticated;

drop policy if exists criar on versoes;
create policy criar on versoes for insert to authenticated with check (
  eh_membro() and autor = auth.uid() and (autor_email is null or autor_email = auth.jwt() ->> 'email')
  and (eh_admin() or eh_robo() or (select count(*) from versoes v where v.autor = auth.uid() and v.criado_em > now() - interval '1 day') < 5));

select 'v47 pronto' as resultado,
       (select count(*) from documentos where uso_ia is not null) as arquivos_marcados,
       (select count(*) from resumos where st_modelo is not null) as temas_no_modelo_novo;
