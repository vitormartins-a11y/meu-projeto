-- v4: administrador, registro de uso, permissões mais rígidas e moderação de imagens
-- Troque o e-mail abaixo se você entra no app com outro e-mail.
create table if not exists admins (email text primary key);
alter table admins enable row level security;
insert into admins (email) values ('vitor.martins@univale.br') on conflict do nothing;
create or replace function eh_admin() returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from admins where lower(email) = lower(coalesce(auth.jwt() ->> 'email', '')));
$$;
revoke all on function eh_admin() from public, anon;
grant execute on function eh_admin() to authenticated;

-- Temas: só o administrador apaga (apagar um tema levaria junto os arquivos de outras pessoas)
drop policy if exists apagar on materias;
create policy apagar on materias for delete to authenticated using (eh_admin());
-- Arquivos: quem enviou ou o administrador
drop policy if exists apagar on documentos;
create policy apagar on documentos for delete to authenticated using (criado_por = auth.uid() or eh_admin());
-- Páginas: cada um só altera as páginas dos próprios arquivos
drop policy if exists atualizar on paginas;
create policy atualizar on paginas for update to authenticated
  using (eh_admin() or exists (select 1 from documentos d where d.id = documento_id and d.criado_por = auth.uid()))
  with check (eh_admin() or exists (select 1 from documentos d where d.id = documento_id and d.criado_por = auth.uid()));
-- Flashcards e questões: os criados à mão só por quem criou (ou o administrador)
drop policy if exists apagar on flashcards;
create policy apagar on flashcards for delete to authenticated using (eh_admin() or (eh_membro() and (criado_por = auth.uid() or origem <> 'ALUNO')));
drop policy if exists apagar on questoes;
create policy apagar on questoes for delete to authenticated using (eh_admin() or (eh_membro() and (criado_por = auth.uid() or origem <> 'ALUNO')));
-- Imagens: ninguém sobrescreve imagem de outra pessoa; só o administrador apaga
drop policy if exists "acervo atualizar imagens" on storage.objects;
drop policy if exists "acervo apagar imagens" on storage.objects;
create policy "acervo apagar imagens" on storage.objects for delete to authenticated using (bucket_id = 'paginas' and eh_admin());

-- Registro de uso: telas abertas e tempo em cada uma (só o administrador lê)
create table if not exists acessos (
  id bigserial primary key, user_id uuid not null default auth.uid(), rota text, materia_id uuid, aba text,
  inicio timestamptz not null default now(), segundos int not null default 0, aparelho text);
create index if not exists acessos_usuario on acessos (user_id, inicio);
alter table acessos enable row level security;
drop policy if exists registrar on acessos;
create policy registrar on acessos for insert to authenticated with check (user_id = auth.uid());
drop policy if exists admin_le on acessos;
create policy admin_le on acessos for select to authenticated using (eh_admin());

-- Registro de envios de material
create table if not exists envios (
  id bigserial primary key, user_id uuid not null default auth.uid(), origem text,
  arquivos int, ok int, pulados int, erros int, midias int, temas text[], em timestamptz default now());
alter table envios enable row level security;
drop policy if exists registrar on envios;
create policy registrar on envios for insert to authenticated with check (user_id = auth.uid());
drop policy if exists admin_le on envios;
create policy admin_le on envios for select to authenticated using (eh_admin());

-- O administrador lê progresso, eventos e denúncias de todos
drop policy if exists admin_le on progresso;
create policy admin_le on progresso for select to authenticated using (eh_admin());
drop policy if exists admin_le on eventos;
create policy admin_le on eventos for select to authenticated using (eh_admin());
drop policy if exists admin_le on reportes;
create policy admin_le on reportes for select to authenticated using (eh_admin());
drop policy if exists admin_apaga on reportes;
create policy admin_apaga on reportes for delete to authenticated using (eh_admin());

-- Moderação: imagens suspeitas ficam escondidas até o administrador liberar
create table if not exists moderacao (
  ref text primary key, user_id uuid default auth.uid(), motivo text, pontuacao real,
  status text not null default 'pendente', criado_em timestamptz default now(), revisado_em timestamptz);
alter table moderacao enable row level security;
drop policy if exists ler on moderacao;
create policy ler on moderacao for select to authenticated using (eh_membro());
drop policy if exists registrar on moderacao;
create policy registrar on moderacao for insert to authenticated with check (eh_membro() and user_id = auth.uid());
drop policy if exists admin_altera on moderacao;
create policy admin_altera on moderacao for update to authenticated using (eh_admin()) with check (eh_admin());

-- Painel do administrador: um resumo por pessoa
create or replace function admin_resumo(dias int default 30) returns json
language plpgsql stable security definer set search_path = public as $$
declare desde timestamptz := now() - make_interval(days => dias); r json;
begin
  if not eh_admin() then raise exception 'Apenas o administrador pode ver este painel.'; end if;
  select coalesce(json_agg(x order by x.ultimo_login desc nulls last), '[]') into r from (
    select u.id, u.email::text as email, u.created_at as criado_em, u.last_sign_in_at as ultimo_login,
      exists (select 1 from membros m where lower(m.email) = lower(u.email)) as membro,
      (select coalesce(sum(a.segundos), 0) from acessos a where a.user_id = u.id and a.inicio >= desde) as segundos,
      (select count(distinct (a.inicio at time zone 'America/Sao_Paulo')::date) from acessos a where a.user_id = u.id and a.inicio >= desde) as dias_ativos,
      (select max(a.inicio + make_interval(secs => a.segundos)) from acessos a where a.user_id = u.id) as ultimo_acesso,
      (select count(*) from documentos d where d.criado_por = u.id) as arquivos,
      (select count(*) from envios e where e.user_id = u.id) as envios,
      (select count(*) from progresso p where p.user_id = u.id and p.tipo = 'q') as questoes,
      (select round(100.0 * avg(case when p.acertou then 1 else 0 end)) from progresso p where p.user_id = u.id and p.tipo = 'q' and p.acertou is not null) as acerto,
      (select count(*) from progresso p where p.user_id = u.id and p.tipo = 'fc') as flashcards,
      (select count(*) from flashcards f where f.criado_por = u.id and f.origem = 'ALUNO')
        + (select count(*) from questoes q where q.criado_por = u.id and q.origem = 'ALUNO') as criados
    from auth.users u) x;
  return r;
end $$;
revoke all on function admin_resumo(int) from public, anon;
grant execute on function admin_resumo(int) to authenticated;

-- Painel do administrador: detalhes de uma pessoa
create or replace function admin_usuario(uid uuid, dias int default 30) returns json
language plpgsql stable security definer set search_path = public as $$
declare desde timestamptz := now() - make_interval(days => dias); r json;
begin
  if not eh_admin() then raise exception 'Apenas o administrador pode ver este painel.'; end if;
  select json_build_object(
    'temas', (select coalesce(json_agg(t), '[]') from (
        select a.materia_id, m.materia, m.periodo, sum(a.segundos) as segundos, count(*) as visitas, max(a.inicio) as ultima
        from acessos a left join materias m on m.id = a.materia_id
        where a.user_id = uid and a.inicio >= desde and a.materia_id is not null
        group by a.materia_id, m.materia, m.periodo order by sum(a.segundos) desc limit 40) t),
    'secoes', (select coalesce(json_agg(s), '[]') from (
        select a.aba, sum(a.segundos) as segundos, count(*) as visitas from acessos a
        where a.user_id = uid and a.inicio >= desde group by a.aba order by sum(a.segundos) desc) s),
    'por_dia', (select coalesce(json_agg(d), '[]') from (
        select (a.inicio at time zone 'America/Sao_Paulo')::date as dia, sum(a.segundos) as segundos from acessos a
        where a.user_id = uid and a.inicio >= desde group by 1 order by 1) d),
    'recentes', (select coalesce(json_agg(v), '[]') from (
        select a.inicio, a.segundos, a.aba, a.rota, m.materia from acessos a left join materias m on m.id = a.materia_id
        where a.user_id = uid order by a.inicio desc limit 80) v),
    'envios', (select coalesce(json_agg(e), '[]') from (select * from envios e where e.user_id = uid order by e.em desc limit 40) e),
    'aparelhos', (select coalesce(json_agg(distinct a.aparelho), '[]') from acessos a where a.user_id = uid and a.aparelho is not null)
  ) into r;
  return r;
end $$;
revoke all on function admin_usuario(uuid, int) from public, anon;
grant execute on function admin_usuario(uuid, int) to authenticated;
