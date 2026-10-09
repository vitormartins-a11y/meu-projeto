-- v18: site mais rápido e sem "statement timeout"
-- 1) Índices que faltavam: contar os arquivos de cada tema e ler as listas grandes em ordem passam a usar índice
--    (antes o banco varria a tabela inteira a cada página aberta).
-- 2) Regras de acesso (quem pode ler o quê): a conferência "é da turma?" era feita de novo PARA CADA LINHA lida
--    (milhares de vezes por página). Agora é feita uma vez por consulta. Quem pode ver o quê NÃO muda.
-- Pode rodar mais de uma vez sem problema.

create index if not exists documentos_materia on documentos (materia_id);
create index if not exists documentos_criado on documentos (criado_em);
create index if not exists flashcards_criado on flashcards (criado_em);
create index if not exists questoes_criado on questoes (criado_em);
create index if not exists membros_email_lower on membros (lower(email));
do $$ begin
  if to_regclass('public.midias') is not null then
    execute 'create index if not exists midias_materia on midias (materia_id)';
  end if;
end $$;

-- regras de acesso: eh_membro(), eh_admin(), eh_robo() e auth.uid() calculados uma vez por consulta
do $$
declare p record; q text; c text; cmd text;
begin
  for p in select schemaname, tablename, policyname, qual, with_check from pg_policies where schemaname = 'public' loop
    q := regexp_replace(coalesce(p.qual, ''), '(?<!SELECT )\m(eh_membro|eh_admin|eh_robo)\(\)', '(SELECT \1())', 'g');
    q := regexp_replace(q, '(?<!SELECT )auth\.uid\(\)', '(SELECT auth.uid())', 'g');
    c := regexp_replace(coalesce(p.with_check, ''), '(?<!SELECT )\m(eh_membro|eh_admin|eh_robo)\(\)', '(SELECT \1())', 'g');
    c := regexp_replace(c, '(?<!SELECT )auth\.uid\(\)', '(SELECT auth.uid())', 'g');
    if q is distinct from coalesce(p.qual, '') or c is distinct from coalesce(p.with_check, '') then
      cmd := format('alter policy %I on %I.%I', p.policyname, p.schemaname, p.tablename);
      if p.qual is not null then cmd := cmd || format(' using (%s)', q); end if;
      if p.with_check is not null then cmd := cmd || format(' with check (%s)', c); end if;
      begin execute cmd; exception when others then raise notice 'não ajustei %: %', p.policyname, sqlerrm; end;
    end if;
  end loop;
end $$;

analyze materias; analyze documentos; analyze resumos; analyze flashcards; analyze questoes; analyze membros;

select case when exists (select 1 from information_schema.columns where table_schema = 'public' and table_name = 'resumos' and column_name = 'st_versao')
  then 'Pronto. (o SQL v14 também já está rodado)' else 'Pronto, mas FALTA rodar o SQL v14: sem ele o site continua lendo os temas inteiros e fica lento.' end as resultado;
