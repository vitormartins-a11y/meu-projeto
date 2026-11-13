-- v52: acervo geral do curso (Medicina), bulário e páginas do acervo geral.
-- * Acervo geral: uma "turma" especial (geral = true) do curso Medicina, que o administrador cuida. Ali entram as apostilas
--   das especialidades feitas do material do administrador, organizadas pelos sumários. Só o administrador envia,
--   apaga e edita. Qualquer pessoa com conta (não bloqueada) só LÊ: as regras novas são só de leitura (select).
-- * Bulário: uma bula por remédio. Todos leem; só o administrador cria, muda e apaga.
-- * Páginas do acervo geral (ex.: Vacinas): texto que o administrador escreve. Todos leem; só o administrador muda.
-- Nada é apagado. Pode rodar mais de uma vez sem problema.

-- 1) A turma do acervo geral
alter table turmas add column if not exists geral boolean not null default false;
do $$
declare cur uuid; dono_id uuid;
begin
  select id into cur from cursos where lower(nome) = 'medicina';
  if cur is not null and not exists (select 1 from turmas where geral and curso_id = cur) then
    select u.id into dono_id from auth.users u join admins a on lower(a.email) = lower(u.email) order by u.created_at limit 1;
    if dono_id is null then select dono into dono_id from turmas where curso_id = cur order by criado_em limit 1; end if;
    if dono_id is not null then
      insert into turmas (curso_id, nome, dono, geral) values (cur, 'Acervo geral de Medicina', dono_id, true)
        on conflict do nothing;
      update turmas set geral = true where curso_id = cur and lower(nome) = lower('Acervo geral de Medicina');
    end if;
  end if;
end $$;

create or replace function turmas_gerais() returns uuid[]
language sql stable security definer set search_path = public as $$
  select case when auth.uid() is null or exists (select 1 from bloqueados where user_id = auth.uid()) then '{}'::uuid[]
    else (select coalesce(array_agg(id), '{}') from turmas where geral) end;
$$;
create or replace function materias_gerais() returns uuid[]
language sql stable security definer set search_path = public as $$
  select coalesce(array_agg(id), '{}') from materias where turma_id = any (turmas_gerais());
$$;
grant execute on function turmas_gerais(), materias_gerais() to authenticated;

-- 2) Leitura do acervo geral para quem tem conta: só "select" (enviar, mudar e apagar continuam com as regras de antes)
drop policy if exists ler_geral on materias;
create policy ler_geral on materias for select to authenticated using (turma_id = any (coalesce((select turmas_gerais()), '{}'::uuid[])));
do $$
declare t record;
begin
  for t in
    select c.table_name from information_schema.columns c
    join pg_tables p on p.schemaname = 'public' and p.tablename = c.table_name
    where c.table_schema = 'public' and c.column_name = 'materia_id' and p.rowsecurity
      and c.table_name not in ('progresso', 'eventos', 'acessos', 'anotacoes', 'pastas_pessoais', 'materias')
  loop
    begin
      execute format('drop policy if exists ler_geral on public.%I', t.table_name);
      execute format('create policy ler_geral on public.%I for select to authenticated using (materia_id = any (coalesce((select materias_gerais()), ''{}''::uuid[])))', t.table_name);
    exception when others then raise notice 'não criei a leitura do acervo geral em %: %', t.table_name, sqlerrm;
    end;
  end loop;
end $$;

-- 3) Bulário
create table if not exists bulas (
  id uuid primary key default gen_random_uuid(),
  nome text not null,
  chave text not null,                       -- nome sem acento, minúsculo e sem espaços repetidos (não deixa repetir)
  dados jsonb not null default '{}'::jsonb,  -- campos da bula (nome comercial, apresentações, posologia...)
  atualizado_em timestamptz default now(),
  atualizado_por uuid default auth.uid());
create unique index if not exists bulas_chave on bulas (chave);
alter table bulas enable row level security;
drop policy if exists ler on bulas;
create policy ler on bulas for select to authenticated using (not exists (select 1 from bloqueados where user_id = (select auth.uid())));
drop policy if exists admin on bulas;
create policy admin on bulas for all to authenticated using ((select eh_admin())) with check ((select eh_admin()));

-- 4) Páginas do acervo geral (Vacinas e o que vier depois)
create table if not exists acervo_geral_paginas (
  chave text primary key,
  dados jsonb not null default '{}'::jsonb,
  atualizado_em timestamptz default now(),
  atualizado_por uuid default auth.uid());
alter table acervo_geral_paginas enable row level security;
drop policy if exists ler on acervo_geral_paginas;
create policy ler on acervo_geral_paginas for select to authenticated using (not exists (select 1 from bloqueados where user_id = (select auth.uid())));
drop policy if exists admin on acervo_geral_paginas;
create policy admin on acervo_geral_paginas for all to authenticated using ((select eh_admin())) with check ((select eh_admin()));


-- 5) Apostila editada à mão pelo administrador: uma coluna pequena para a fila do refazer saber sem baixar a apostila
alter table resumos add column if not exists st_editado text generated always as (dados->>'editadoManual') stored;

select 'v52 ok' as resultado, (select count(*) from turmas where geral) as acervos_gerais;
