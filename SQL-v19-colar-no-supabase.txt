-- v19: cursos e turmas (o site deixa de ser uma turma só)
-- * Cursos (Medicina, Direito...): qualquer pessoa sugere; só aparece depois que o administrador aprova.
-- * Turmas dentro do curso: qualquer pessoa cria e vira a dona. Entra quem digita o código ou quem a dona aceita.
-- * Cada turma tem o seu acervo (temas, arquivos, apostilas, flashcards, questões) e a sua lista de temas.
--   Uma turma não vê o material da outra. O administrador vê tudo. Anamneses, OSCE e anotações continuam só da pessoa.
-- * A turma de hoje vira "8° período UNIVALE", no curso Medicina, com o mesmo código. Nada é apagado.
-- Pode rodar mais de uma vez sem problema.

-- 1) Tabelas
create table if not exists cursos (
  id uuid primary key default gen_random_uuid(),
  nome text not null,
  area text not null default 'outra' check (area in ('saude', 'outra')),
  aprovado boolean not null default false,
  perfil_ia text not null default '',
  criado_por uuid default auth.uid(),
  criado_em timestamptz default now());
create unique index if not exists cursos_nome on cursos (lower(nome));
create table if not exists turmas (
  id uuid primary key default gen_random_uuid(),
  curso_id uuid not null references cursos on delete cascade,
  nome text not null,
  codigo text not null default upper(substr(md5(random()::text), 1, 6)),
  dono uuid not null default auth.uid(),
  perfil_ia jsonb not null default '{}'::jsonb,
  criado_em timestamptz default now());
create unique index if not exists turmas_nome on turmas (curso_id, lower(nome));
create table if not exists turma_membros (
  turma_id uuid not null references turmas on delete cascade,
  user_id uuid not null references auth.users on delete cascade,
  email text, nome text,
  papel text not null default 'membro' check (papel in ('dono', 'membro')),
  status text not null default 'pendente' check (status in ('pendente', 'ativo')),
  criado_em timestamptz default now(),
  primary key (turma_id, user_id));
create index if not exists turma_membros_usuario on turma_membros (user_id);
create table if not exists bloqueados (user_id uuid primary key, motivo text, em timestamptz default now());

-- 2) A turma de hoje: curso Medicina + "8° período UNIVALE" (mesmo código), dona = administrador
insert into cursos (nome, area, aprovado, perfil_ia)
select 'Medicina', 'saude', true,
  'Curso de Medicina. Use a terminologia médica correta e as diretrizes brasileiras atuais (Ministério da Saúde, sociedades de especialidade). '
  || 'Em tratamento, dê a primeira escolha e as alternativas com dose, via e duração quando o material trouxer; destaque critérios diagnósticos, '
  || 'sinais de alarme, condutas e as pegadinhas que mais caem em prova.'
where not exists (select 1 from cursos where lower(nome) = 'medicina');
do $$
declare cur uuid; dono_id uuid; t uuid; cod text;
begin
  select id into cur from cursos where lower(nome) = 'medicina';
  select valor into t from config where chave = 'turma_padrao';
  if t is null or not exists (select 1 from turmas where id = t) then
    select u.id into dono_id from auth.users u join admins a on lower(a.email) = lower(u.email) order by u.created_at limit 1;
    if dono_id is null then select id into dono_id from auth.users order by created_at limit 1; end if;
    select valor into cod from config where chave = 'codigo_turma';
    insert into turmas (curso_id, nome, codigo, dono) values (cur, '8° período UNIVALE', coalesce(nullif(trim(cod), ''), upper(substr(md5(random()::text), 1, 6))), dono_id)
      on conflict do nothing returning id into t;
    if t is null then select id into t from turmas where curso_id = cur and lower(nome) = lower('8° período UNIVALE'); end if;
    insert into config (chave, valor) values ('turma_padrao', t) on conflict (chave) do update set valor = excluded.valor;
  end if;
end $$;
create or replace function turma_padrao() returns uuid
language sql stable security definer set search_path = public as $$ select valor::uuid from config where chave = 'turma_padrao'; $$;

-- 3) Cada tema pertence a uma turma (os de hoje vão para a turma padrão)
alter table materias add column if not exists turma_id uuid references turmas on delete cascade;
update materias set turma_id = turma_padrao() where turma_id is null;
create index if not exists materias_turma on materias (turma_id);
create or replace function materia_turma_padrao() returns trigger
language plpgsql security definer set search_path = public as $$
begin if new.turma_id is null then new.turma_id := turma_padrao(); end if; return new; end $$;
drop trigger if exists materia_turma on materias;
create trigger materia_turma before insert on materias for each row execute function materia_turma_padrao();
-- o mesmo nome de tema pode existir em turmas diferentes
alter table materias drop constraint if exists materias_lugar_unico;
alter table materias drop constraint if exists materias_periodo_disciplina_materia_key;
do $$ begin
  if exists (select 1 from information_schema.columns where table_name = 'materias' and column_name = 'acervo') then
    execute 'alter table materias add constraint materias_lugar_unico unique (turma_id, acervo, colecao, periodo, disciplina, materia)';
  else
    execute 'alter table materias add constraint materias_lugar_unico unique (turma_id, periodo, disciplina, materia)';
  end if;
exception when duplicate_table or duplicate_object then null; end $$;
-- envios, fila de envios do robô e uso da IA também guardam a turma
alter table envios add column if not exists turma_id uuid;
alter table envios add column if not exists link text;
do $$ begin
  if to_regclass('public.envios_fila') is not null then execute 'alter table envios_fila add column if not exists turma_id uuid'; end if;
end $$;
alter table uso_ia add column if not exists turma_id uuid;
alter table uso_ia add column if not exists pediu uuid;            -- quem fez o pedido (user_id é o dono da chave usada)
create index if not exists uso_ia_pediu on uso_ia (pediu, em);

-- 4) Quem está em qual turma
create or replace function eh_robo() returns boolean
language sql stable security definer set search_path = public as $$
  select lower(coalesce(auth.jwt() ->> 'email', '')) = 'robo-ia@example.com';
$$;
-- turmas que a pessoa pode ver: as dela (ativas) + a turma padrão para quem já estava na lista antiga de membros.
-- Administrador e robô: todas. Bloqueado: nenhuma.
create or replace function minhas_turmas() returns uuid[]
language sql stable security definer set search_path = public as $$
  select case
    when exists (select 1 from bloqueados where user_id = auth.uid()) then '{}'::uuid[]
    when eh_admin() or eh_robo() then (select coalesce(array_agg(id), '{}') from turmas)
    else (select coalesce(array_agg(distinct t), '{}') from (
      select turma_id as t from turma_membros where user_id = auth.uid() and status = 'ativo'
      union all
      select turma_padrao() where exists (select 1 from membros where lower(email) = lower(coalesce(auth.jwt() ->> 'email', '')))) x where t is not null)
  end;
$$;
create or replace function materias_visiveis() returns uuid[]
language sql stable security definer set search_path = public as $$
  select coalesce(array_agg(id), '{}') from materias where turma_id = any (minhas_turmas());
$$;
-- "é da turma?" agora quer dizer: está em pelo menos uma turma
create or replace function eh_membro() returns boolean
language sql stable security definer set search_path = public as $$ select cardinality(minhas_turmas()) > 0; $$;
create or replace function eh_dono(t uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select eh_admin() or exists (select 1 from turmas where id = t and dono = auth.uid())
    or exists (select 1 from turma_membros where turma_id = t and user_id = auth.uid() and papel = 'dono' and status = 'ativo');
$$;
revoke all on function minhas_turmas() from public, anon;
revoke all on function materias_visiveis() from public, anon;
revoke all on function eh_dono(uuid) from public, anon;
grant execute on function minhas_turmas(), materias_visiveis(), eh_dono(uuid), eh_membro(), turma_padrao() to authenticated;

-- membros da lista antiga que já têm conta entram na turma padrão
insert into turma_membros (turma_id, user_id, email, papel, status)
select turma_padrao(), u.id, u.email, case when u.id = (select dono from turmas where id = turma_padrao()) then 'dono' else 'membro' end, 'ativo'
from auth.users u join membros m on lower(m.email) = lower(u.email)
on conflict (turma_id, user_id) do nothing;
insert into turma_membros (turma_id, user_id, email, papel, status)
select id, dono, (select email from auth.users where id = dono), 'dono', 'ativo' from turmas where dono is not null
on conflict (turma_id, user_id) do update set papel = 'dono', status = 'ativo';

-- 5) Regras de acesso das tabelas novas
alter table cursos enable row level security;
alter table turmas enable row level security;
alter table turma_membros enable row level security;
alter table bloqueados enable row level security;
drop policy if exists ler on cursos;
create policy ler on cursos for select to authenticated using (aprovado or criado_por = (select auth.uid()) or (select eh_admin()));
drop policy if exists sugerir on cursos;
create policy sugerir on cursos for insert to authenticated with check (not aprovado and criado_por = (select auth.uid()));
drop policy if exists admin_muda on cursos;
create policy admin_muda on cursos for update to authenticated using ((select eh_admin())) with check ((select eh_admin()));
drop policy if exists admin_apaga on cursos;
create policy admin_apaga on cursos for delete to authenticated using ((select eh_admin()));
drop policy if exists ler on turmas;
create policy ler on turmas for select to authenticated using (true);           -- nomes das turmas aparecem para escolher (o código não)
drop policy if exists dono_muda on turmas;
create policy dono_muda on turmas for update to authenticated using (eh_dono(id)) with check (eh_dono(id));
drop policy if exists dono_apaga on turmas;
create policy dono_apaga on turmas for delete to authenticated using (eh_dono(id));
-- o código da turma não pode ser lido por ninguém pela tabela (só pela função, para a dona)
revoke select on turmas from anon, authenticated;
grant select (id, curso_id, nome, dono, perfil_ia, criado_em) on turmas to authenticated;
revoke insert on turmas from anon, authenticated;
grant update (nome, perfil_ia) on turmas to authenticated;
drop policy if exists ler on turma_membros;
create policy ler on turma_membros for select to authenticated using (
  user_id = (select auth.uid()) or eh_dono(turma_id) or (status = 'ativo' and turma_id = any (coalesce((select minhas_turmas()), '{}'::uuid[]))));
drop policy if exists sair_ou_dono on turma_membros;
create policy sair_ou_dono on turma_membros for delete to authenticated using (user_id = (select auth.uid()) or eh_dono(turma_id));
drop policy if exists admin on bloqueados;
create policy admin on bloqueados for all to authenticated using ((select eh_admin())) with check ((select eh_admin()));

-- 6) Ações (funções): criar turma, entrar com código, pedir para entrar, aceitar, trocar código, sugerir e aprovar curso
create or replace function criar_turma(curso uuid, p_nome text) returns uuid
language plpgsql security definer set search_path = public as $$
declare t uuid;
begin
  if auth.uid() is null then raise exception 'Entre na sua conta primeiro.'; end if;
  if exists (select 1 from bloqueados where user_id = auth.uid()) then raise exception 'Conta bloqueada.'; end if;
  if not exists (select 1 from cursos where id = curso and aprovado) then raise exception 'Curso não encontrado ou ainda não aprovado.'; end if;
  if length(trim(coalesce(p_nome, ''))) < 3 then raise exception 'Dê um nome para a turma (ex.: 8° período UNIVALE).'; end if;
  insert into turmas (curso_id, nome, dono) values (curso, trim(p_nome), auth.uid()) returning id into t;
  insert into turma_membros (turma_id, user_id, email, nome, papel, status)
    values (t, auth.uid(), auth.jwt() ->> 'email', auth.jwt() -> 'user_metadata' ->> 'full_name', 'dono', 'ativo');
  return t;
exception when unique_violation then raise exception 'Já existe uma turma com esse nome neste curso.';
end $$;
create or replace function entrar_turma(t uuid, codigo text) returns boolean
language plpgsql security definer set search_path = public as $$
declare certo text;
begin
  if auth.uid() is null or exists (select 1 from bloqueados where user_id = auth.uid()) then return false; end if;
  select turmas.codigo into certo from turmas where id = t;
  if certo is not null and upper(trim(codigo)) = upper(trim(certo)) then
    insert into turma_membros (turma_id, user_id, email, nome, status)
      values (t, auth.uid(), auth.jwt() ->> 'email', auth.jwt() -> 'user_metadata' ->> 'full_name', 'ativo')
      on conflict (turma_id, user_id) do update set status = 'ativo';
    return true;
  end if;
  perform pg_sleep(1);  -- atrasa quem tenta adivinhar
  return false;
end $$;
create or replace function pedir_entrada(t uuid) returns void
language plpgsql security definer set search_path = public as $$
begin
  if auth.uid() is null or exists (select 1 from bloqueados where user_id = auth.uid()) then raise exception 'Não foi possível pedir.'; end if;
  insert into turma_membros (turma_id, user_id, email, nome, status)
    values (t, auth.uid(), auth.jwt() ->> 'email', auth.jwt() -> 'user_metadata' ->> 'full_name', 'pendente')
    on conflict (turma_id, user_id) do nothing;
end $$;
create or replace function responder_pedido(t uuid, u uuid, aceitar boolean) returns void
language plpgsql security definer set search_path = public as $$
begin
  if not eh_dono(t) then raise exception 'Só a dona da turma (ou o administrador) pode aceitar.'; end if;
  if aceitar then update turma_membros set status = 'ativo' where turma_id = t and user_id = u;
  else delete from turma_membros where turma_id = t and user_id = u and status = 'pendente'; end if;
end $$;
create or replace function codigo_da_turma(t uuid) returns text
language plpgsql security definer set search_path = public as $$
begin if not eh_dono(t) then raise exception 'Só a dona da turma vê o código.'; end if; return (select codigo from turmas where id = t); end $$;
create or replace function trocar_codigo(t uuid, novo text) returns text
language plpgsql security definer set search_path = public as $$
declare c text := upper(regexp_replace(coalesce(novo, ''), '\s', '', 'g'));
begin
  if not eh_dono(t) then raise exception 'Só a dona da turma muda o código.'; end if;
  if length(c) < 4 then c := upper(substr(md5(random()::text), 1, 6)); end if;
  update turmas set codigo = c where id = t;
  if t = turma_padrao() then update config set valor = c where chave = 'codigo_turma'; end if;
  return c;
end $$;
create or replace function sugerir_curso(p_nome text, p_area text) returns uuid
language plpgsql security definer set search_path = public as $$
declare c uuid;
begin
  if auth.uid() is null then raise exception 'Entre na sua conta primeiro.'; end if;
  if length(trim(coalesce(p_nome, ''))) < 3 then raise exception 'Escreva o nome do curso.'; end if;
  select id into c from cursos where lower(cursos.nome) = lower(trim(p_nome));
  if c is not null then return c; end if;
  insert into cursos (nome, area, aprovado, criado_por) values (trim(p_nome), case when p_area = 'saude' then 'saude' else 'outra' end, false, auth.uid()) returning id into c;
  return c;
end $$;
create or replace function aprovar_curso(c uuid, aprovar boolean, p_area text, p_perfil text) returns void
language plpgsql security definer set search_path = public as $$
begin
  if not eh_admin() then raise exception 'Só o administrador aprova cursos.'; end if;
  if aprovar then update cursos set aprovado = true, area = case when p_area = 'saude' then 'saude' else 'outra' end, perfil_ia = coalesce(p_perfil, perfil_ia) where id = c;
  else delete from cursos where id = c and not aprovado; end if;
end $$;
-- lista de temas da turma (a dona edita; a turma lê)
create or replace function salvar_lista_turma(t uuid, p_texto text) returns void
language plpgsql security definer set search_path = public as $$
begin
  if not eh_dono(t) then raise exception 'Só a dona da turma muda a lista de temas.'; end if;
  insert into listas (chave, texto, atualizado_em, atualizado_por) values ('temas:' || t, p_texto, now(), auth.uid())
    on conflict (chave) do update set texto = excluded.texto, atualizado_em = now(), atualizado_por = auth.uid();
end $$;
-- bloquear alguém (administrador): sai de todas as turmas e não entra em nenhuma
create or replace function bloquear(u uuid, p_motivo text) returns void
language plpgsql security definer set search_path = public as $$
begin
  if not eh_admin() then raise exception 'Só o administrador bloqueia.'; end if;
  insert into bloqueados (user_id, motivo) values (u, p_motivo) on conflict (user_id) do update set motivo = excluded.motivo, em = now();
  delete from turma_membros where user_id = u;
end $$;
do $$ declare f text; begin
  foreach f in array array['criar_turma(uuid, text)', 'entrar_turma(uuid, text)', 'pedir_entrada(uuid)', 'responder_pedido(uuid, uuid, boolean)', 'codigo_da_turma(uuid)',
    'trocar_codigo(uuid, text)', 'sugerir_curso(text, text)', 'aprovar_curso(uuid, boolean, text, text)', 'salvar_lista_turma(uuid, text)', 'bloquear(uuid, text)'] loop
    execute format('revoke all on function %s from public, anon', f);
    execute format('grant execute on function %s to authenticated', f);
  end loop;
end $$;
-- código antigo (tela "digite o código da turma"): continua valendo para a turma padrão
create or replace function entrar_na_turma(codigo text) returns boolean
language plpgsql security definer set search_path = public as $$
begin return entrar_turma(turma_padrao(), codigo); end $$;

-- 7) Regras de acesso do acervo: em vez de "é da turma?", "é da turma DESTE tema?"
--    (tabelas com materia_id: arquivos, páginas, apostilas, flashcards, questões, mídias, falhas, versões)
do $$
declare p record; q text; c text; cmd text; tem_mat boolean;
begin
  for p in select schemaname, tablename, policyname, qual, with_check from pg_policies where schemaname = 'public'
           and tablename not in ('cursos', 'turmas', 'turma_membros', 'bloqueados') loop
    tem_mat := exists (select 1 from information_schema.columns where table_schema = 'public' and table_name = p.tablename and column_name = 'materia_id');
    if p.tablename <> 'materias' and not tem_mat then continue; end if;
    if p.tablename in ('progresso', 'eventos', 'acessos', 'anotacoes', 'pastas_pessoais') then continue; end if;   -- coisas da própria pessoa
    q := coalesce(p.qual, ''); c := coalesce(p.with_check, '');
    if p.tablename = 'materias' then
      q := regexp_replace(q, '\(\s*SELECT eh_membro\(\) AS eh_membro\)|\meh_membro\(\)', '(turma_id = ANY (COALESCE(( SELECT minhas_turmas() AS minhas_turmas), ''{}''::uuid[])))', 'g');
      c := regexp_replace(c, '\(\s*SELECT eh_membro\(\) AS eh_membro\)|\meh_membro\(\)', '(turma_id = ANY (COALESCE(( SELECT minhas_turmas() AS minhas_turmas), ''{}''::uuid[])))', 'g');
    else
      q := regexp_replace(q, '\(\s*SELECT eh_membro\(\) AS eh_membro\)|\meh_membro\(\)', '(materia_id = ANY (COALESCE(( SELECT materias_visiveis() AS materias_visiveis), ''{}''::uuid[])))', 'g');
      c := regexp_replace(c, '\(\s*SELECT eh_membro\(\) AS eh_membro\)|\meh_membro\(\)', '(materia_id = ANY (COALESCE(( SELECT materias_visiveis() AS materias_visiveis), ''{}''::uuid[])))', 'g');
    end if;
    if q is distinct from coalesce(p.qual, '') or c is distinct from coalesce(p.with_check, '') then
      cmd := format('alter policy %I on %I.%I', p.policyname, p.schemaname, p.tablename);
      if p.qual is not null then cmd := cmd || format(' using (%s)', q); end if;
      if p.with_check is not null then cmd := cmd || format(' with check (%s)', c); end if;
      begin execute cmd; exception when others then raise notice 'não ajustei % em %: %', p.policyname, p.tablename, sqlerrm; end;
    end if;
  end loop;
end $$;
-- a dona da turma também pode apagar e mover temas da turma dela
drop policy if exists dono_apaga on materias;
create policy dono_apaga on materias for delete to authenticated using (eh_dono(turma_id));
drop policy if exists dono_altera on materias;
create policy dono_altera on materias for update to authenticated using (eh_dono(turma_id)) with check (eh_dono(turma_id));

-- 8) Painel do administrador: turmas e uso de IA por pessoa
create or replace function admin_turmas() returns table (id uuid, curso text, area text, nome text, dono_email text, membros bigint, pendentes bigint,
  temas bigint, pedidos_ia_30d bigint, tokens_30d bigint, criado_em timestamptz)
language sql stable security definer set search_path = public as $$
  select t.id, c.nome, c.area, t.nome, (select email from auth.users where id = t.dono),
    (select count(*) from turma_membros m where m.turma_id = t.id and m.status = 'ativo'),
    (select count(*) from turma_membros m where m.turma_id = t.id and m.status = 'pendente'),
    (select count(*) from materias x where x.turma_id = t.id),
    (select count(*) from uso_ia u where u.turma_id = t.id and u.em > now() - interval '30 days'),
    (select coalesce(sum(coalesce(u.tokens_in, 0) + coalesce(u.tokens_out, 0)), 0) from uso_ia u where u.turma_id = t.id and u.em > now() - interval '30 days'),
    t.criado_em
  from turmas t join cursos c on c.id = t.curso_id where eh_admin() order by c.nome, t.nome;
$$;
create or replace function admin_tokens(desde timestamptz) returns table (user_id uuid, email text, turmas text, pedidos bigint, recusados bigint,
  tokens_in bigint, tokens_out bigint, ultimo timestamptz)
language sql stable security definer set search_path = public as $$
  select u.pediu, (select a.email from auth.users a where a.id = u.pediu),
    (select string_agg(distinct t.nome, ', ') from turma_membros m join turmas t on t.id = m.turma_id where m.user_id = u.pediu and m.status = 'ativo'),
    count(*) filter (where u.ok), count(*) filter (where not u.ok),
    coalesce(sum(u.tokens_in), 0), coalesce(sum(u.tokens_out), 0), max(u.em)
  from uso_ia u where u.em >= desde and u.pediu is not null and eh_admin()
  group by u.pediu order by coalesce(sum(u.tokens_in), 0) + coalesce(sum(u.tokens_out), 0) desc;
$$;
revoke all on function admin_turmas() from public, anon;
revoke all on function admin_tokens(timestamptz) from public, anon;
grant execute on function admin_turmas(), admin_tokens(timestamptz) to authenticated;
-- renomear coleção: só dentro de uma turma
create or replace function renomear_colecao(antigo text, novo text, turma uuid) returns int
language plpgsql security definer set search_path = public as $$
declare n int;
begin
  if not eh_dono(coalesce(turma, turma_padrao())) then raise exception 'Só a dona da turma (ou o administrador) renomeia coleções.'; end if;
  if coalesce(trim(novo), '') = '' then raise exception 'O nome novo não pode ficar vazio.'; end if;
  update materias set colecao = trim(novo) where acervo = 'faculdade' and colecao = antigo and turma_id = coalesce(turma, turma_padrao());
  get diagnostics n = row_count; return n;
end $$;
revoke all on function renomear_colecao(text, text, uuid) from public, anon;
grant execute on function renomear_colecao(text, text, uuid) to authenticated;

analyze materias; analyze turma_membros;
select 'Pronto: ' || (select count(*) from cursos) || ' curso(s), ' || (select count(*) from turmas) || ' turma(s), '
  || (select count(*) from turma_membros where status = 'ativo') || ' pessoa(s) nas turmas, '
  || (select count(*) from materias where turma_id = turma_padrao()) || ' tema(s) na turma ' || (select nome from turmas where id = turma_padrao()) || '.' as resultado;
