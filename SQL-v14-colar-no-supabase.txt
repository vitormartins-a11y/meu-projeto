-- v14: site mais leve para o banco (abre mais rápido e não sobrecarrega o plano grátis)
-- Para saber se cada tema já está publicado, o site lia o conteúdo INTEIRO de todos os temas (apostila, rascunhos)
-- a cada página aberta, e o robô a cada rodada. Agora essas informações ficam em colunas pequenas, preenchidas
-- sozinhas pelo banco quando o tema é salvo, e só elas são lidas. Nada muda no conteúdo.
-- Pode demorar um pouco na primeira vez (o banco preenche as colunas de todos os temas). Pode rodar mais de uma vez.
alter table resumos
  add column if not exists st_versao int generated always as (case when (dados->>'versao') ~ '^[0-9]+$' then (dados->>'versao')::int end) stored,
  add column if not exists st_qversao int generated always as (case when (dados->>'qversao') ~ '^[0-9]+$' then (dados->>'qversao')::int end) stored,
  add column if not exists st_gerado_em text generated always as (dados->>'geradoEm') stored,
  add column if not exists st_docs jsonb generated always as (dados->'docs') stored,
  add column if not exists st_ntrechos int generated always as (case when (dados->'rascunho'->>'nTrechos') ~ '^[0-9]+$' then (dados->'rascunho'->>'nTrechos')::int end) stored,
  add column if not exists st_feitas int generated always as (case when (dados->'rascunho'->>'feitas') ~ '^[0-9]+$' then (dados->'rascunho'->>'feitas')::int end) stored,
  add column if not exists st_falta jsonb generated always as (dados->'rascunho'->'falta') stored,
  add column if not exists st_ocupado jsonb generated always as (dados->'ocupado') stored;

-- quantas questões cada tema tem (a tela "Hoje" lia todas as questões, uma por uma, só para contar)
create index if not exists questoes_materia on questoes (materia_id);
create index if not exists flashcards_materia on flashcards (materia_id);
create or replace function contar_por_tema(tabela text)
returns table (materia_id uuid, n bigint) language plpgsql stable security definer set search_path = public as $$
begin
  if not eh_membro() then return; end if;
  if tabela = 'questoes' then return query select q.materia_id, count(*) from questoes q group by q.materia_id;
  elsif tabela = 'flashcards' then return query select f.materia_id, count(*) from flashcards f group by f.materia_id;
  end if;
end $$;
revoke all on function contar_por_tema(text) from public, anon;
grant execute on function contar_por_tema(text) to authenticated;
