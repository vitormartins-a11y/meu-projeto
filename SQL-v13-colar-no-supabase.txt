-- v13: a página de Administração voltou a abrir rápido
-- O resumo por pessoa contava, para CADA conta, os arquivos, as questões e os flashcards lendo as tabelas inteiras
-- (sem índice). Com o acervo maior, passava do limite de tempo do Supabase: "canceling statement due to statement
-- timeout". Agora cada tabela é lida uma vez só, e as colunas usadas têm índice. O resultado é o mesmo.
-- Pode rodar mais de uma vez sem problema.
create index if not exists documentos_criado_por on documentos (criado_por);
create index if not exists envios_usuario on envios (user_id);
create index if not exists progresso_usuario_tipo on progresso (user_id, tipo);
create index if not exists flashcards_aluno on flashcards (criado_por) where origem = 'ALUNO';
create index if not exists questoes_aluno on questoes (criado_por) where origem = 'ALUNO';

create or replace function admin_resumo(dias int default 30) returns json
language plpgsql stable security definer set search_path = public as $$
declare desde timestamptz := now() - make_interval(days => dias); r json;
begin
  if not eh_admin() then raise exception 'Apenas o administrador pode ver este painel.'; end if;
  with ac as (
    select a.user_id,
           sum(a.segundos) filter (where a.inicio >= desde) as segundos,
           count(distinct (a.inicio at time zone 'America/Sao_Paulo')::date) filter (where a.inicio >= desde) as dias_ativos,
           max(a.inicio + make_interval(secs => a.segundos)) as ultimo_acesso
    from acessos a group by a.user_id),
  doc as (select d.criado_por as uid, count(*) as n from documentos d group by d.criado_por),
  env as (select e.user_id as uid, count(*) as n from envios e group by e.user_id),
  pr as (
    select p.user_id as uid, count(*) filter (where p.tipo = 'q') as questoes,
           round(100.0 * avg(case when p.acertou then 1 else 0 end) filter (where p.tipo = 'q' and p.acertou is not null)) as acerto,
           count(*) filter (where p.tipo = 'fc') as flashcards
    from progresso p group by p.user_id),
  cr as (
    select z.criado_por as uid, count(*) as n from (
      select f.criado_por from flashcards f where f.origem = 'ALUNO'
      union all select q.criado_por from questoes q where q.origem = 'ALUNO') z group by z.criado_por)
  select coalesce(json_agg(x order by x.ultimo_login desc nulls last), '[]') into r from (
    select u.id, u.email::text as email, u.created_at as criado_em, u.last_sign_in_at as ultimo_login,
      exists (select 1 from membros m where lower(m.email) = lower(u.email)) as membro,
      coalesce(ac.segundos, 0) as segundos, coalesce(ac.dias_ativos, 0) as dias_ativos, ac.ultimo_acesso,
      coalesce(doc.n, 0) as arquivos, coalesce(env.n, 0) as envios,
      coalesce(pr.questoes, 0) as questoes, pr.acerto, coalesce(pr.flashcards, 0) as flashcards,
      coalesce(cr.n, 0) as criados
    from auth.users u
    left join ac on ac.user_id = u.id left join doc on doc.uid = u.id left join env on env.uid = u.id
    left join pr on pr.uid = u.id left join cr on cr.uid = u.id) x;
  return r;
end $$;
revoke all on function admin_resumo(int) from public, anon;
grant execute on function admin_resumo(int) to authenticated;
