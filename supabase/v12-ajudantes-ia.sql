-- v12: chaves dos alunos guardadas para o robô e painel dos ajudantes da IA
-- Pode rodar mais de uma vez sem problema.

-- 1) Cada pedido à IA anota o tema em que trabalhou (para o painel saber em qual documento cada um ajudou)
alter table uso_ia add column if not exists materia_id uuid;
create index if not exists uso_ia_ajuda on uso_ia (user_id, em) where origem in ('chave-propria', 'chave-guardada');
create index if not exists uso_ia_em on uso_ia (em);

-- 2) Chaves que os alunos deixam o robô usar. A chave fica CIFRADA pela função "ia" (sem o segredo do servidor,
--    o texto guardado não serve para nada). Ninguém lê esta tabela pelo app: nem os alunos nem o administrador.
create table if not exists chaves_ia (
  user_id uuid primary key references auth.users on delete cascade,
  cifrada text not null,
  final text,                         -- 4 últimos caracteres, só para a pessoa reconhecer a chave
  chave_id text,                      -- resumo (hash) curto, para o registro de uso
  ativa boolean not null default true,
  recusada_em timestamptz,            -- o Google recusou a chave (apagada ou copiada errada)
  descanso_ate timestamptz,           -- sem cota até esta hora
  ultimo_uso timestamptz,
  criado_em timestamptz default now());
alter table chaves_ia enable row level security;   -- sem nenhuma regra de acesso: só a função "ia" (chave de serviço)
revoke all on chaves_ia from anon, authenticated;

-- a própria pessoa vê a situação da chave dela (nunca a chave)
create or replace function minha_chave_guardada()
returns table (final text, ativa boolean, recusada_em timestamptz, descanso_ate timestamptz, ultimo_uso timestamptz, criado_em timestamptz)
language sql stable security definer set search_path = public as $$
  select final, ativa, recusada_em, descanso_ate, ultimo_uso, criado_em from chaves_ia where user_id = auth.uid();
$$;
revoke all on function minha_chave_guardada() from public, anon;
grant execute on function minha_chave_guardada() to authenticated;

-- quantas chaves guardadas estão prontas para trabalhar agora (o robô usa para decidir quantos temas faz de uma vez)
create or replace function chaves_guardadas_disponiveis() returns int
language sql stable security definer set search_path = public as $$
  select case when eh_membro() then (select count(*)::int from chaves_ia where ativa and recusada_em is null and coalesce(descanso_ate, '-infinity') < now()) else 0 end;
$$;
revoke all on function chaves_guardadas_disponiveis() from public, anon;
grant execute on function chaves_guardadas_disponiveis() to authenticated;

-- a função "ia" pega a chave que está há mais tempo sem uso (duas chamadas ao mesmo tempo nunca pegam a mesma)
create or replace function pegar_chave_guardada(evitar uuid[] default '{}')
returns table (user_id uuid, cifrada text, chave_id text)
language plpgsql security definer set search_path = public as $$
begin
  return query
  update chaves_ia c set ultimo_uso = now()
  where c.user_id = (select k.user_id from chaves_ia k
                     where k.ativa and k.recusada_em is null and coalesce(k.descanso_ate, '-infinity') < now() and not (k.user_id = any(evitar))
                     order by k.ultimo_uso nulls first limit 1 for update skip locked)
  returning c.user_id, c.cifrada, c.chave_id;
end $$;
revoke all on function pegar_chave_guardada(uuid[]) from public, anon, authenticated;
grant execute on function pegar_chave_guardada(uuid[]) to service_role;

-- 3) Painel dos ajudantes (só o administrador). "Ajuda" = pedido feito com a chave de um aluno:
--    "chave-propria" (app aberto no aparelho dele) ou "chave-guardada" (robô usando a chave que ele deixou).
create or replace function ajudantes(desde timestamptz)
returns table (user_id uuid, email text, guardada boolean, guardada_ativa boolean, recusada_em timestamptz, descanso_ate timestamptz,
               aceitos bigint, recusados bigint, cota_dia bigint, chave_recusada bigint, ultimo_em timestamptz, ultimo_ok boolean,
               ultima_origem text, ultima_tarefa text, ultimo_tema text, temas bigint)
language sql stable security definer set search_path = public as $$
  with gente as (
    select k.user_id from chaves_ia k
    union select u.user_id from uso_ia u where u.origem in ('chave-propria', 'chave-guardada') and u.user_id is not null and u.em >= now() - interval '30 days'),
  hoje as (
    select u.user_id, count(*) filter (where u.ok) a, count(*) filter (where not u.ok) r,
           count(*) filter (where u.dia_gemini) c, count(*) filter (where not u.ok and u.status in (401, 502)) cr,
           count(distinct u.materia_id) t
    from uso_ia u where u.origem in ('chave-propria', 'chave-guardada') and u.em >= desde group by u.user_id),
  ultimo as (
    select distinct on (u.user_id) u.user_id, u.em, u.ok, u.origem, u.tarefa, u.materia_id
    from uso_ia u where u.origem in ('chave-propria', 'chave-guardada') and u.user_id is not null order by u.user_id, u.em desc)
  select g.user_id, (select a.email::text from auth.users a where a.id = g.user_id),
         k.user_id is not null, coalesce(k.ativa, false), k.recusada_em, k.descanso_ate,
         coalesce(h.a, 0), coalesce(h.r, 0), coalesce(h.c, 0), coalesce(h.cr, 0),
         l.em, l.ok, l.origem, l.tarefa, (select m.periodo || ' › ' || m.disciplina || ' › ' || m.materia from materias m where m.id = l.materia_id),
         coalesce(h.t, 0)
  from gente g left join chaves_ia k on k.user_id = g.user_id left join hoje h on h.user_id = g.user_id left join ultimo l on l.user_id = g.user_id
  where eh_admin() order by l.em desc nulls last;
$$;
revoke all on function ajudantes(timestamptz) from public, anon;
grant execute on function ajudantes(timestamptz) to authenticated;

-- sessões de ajuda: pedidos com menos de 15 minutos de intervalo contam como a mesma sessão
create or replace function ajuda_sessoes(desde timestamptz, uid uuid default null)
returns table (user_id uuid, email text, fonte text, inicio timestamptz, fim timestamptz, pedidos bigint, aceitos bigint, temas bigint)
language sql stable security definer set search_path = public as $$
  with b as (
    select u.user_id, u.origem, u.em, u.ok, u.materia_id,
           case when lag(u.em) over w is null or u.em - lag(u.em) over w > interval '15 minutes' then 1 else 0 end as novo
    from uso_ia u
    where u.origem in ('chave-propria', 'chave-guardada') and u.user_id is not null and u.em >= desde and (uid is null or u.user_id = uid) and eh_admin()
    window w as (partition by u.user_id, u.origem order by u.em)),
  s as (select b.*, sum(novo) over (partition by b.user_id, b.origem order by b.em) as sessao from b)
  select s.user_id, (select a.email::text from auth.users a where a.id = s.user_id),
         case when s.origem = 'chave-guardada' then 'robô (chave guardada)' else 'app aberto' end,
         min(s.em), max(s.em), count(*), count(*) filter (where s.ok), count(distinct s.materia_id)
  from s group by s.user_id, s.origem, s.sessao order by min(s.em) desc;
$$;
revoke all on function ajuda_sessoes(timestamptz, uuid) from public, anon;
grant execute on function ajuda_sessoes(timestamptz, uuid) to authenticated;

-- em que cada um ajudou: tema por tema (acervo, especialidade, área), e o que fez em cada um
create or replace function ajuda_contribuicoes(desde timestamptz, uid uuid default null)
returns table (user_id uuid, email text, materia_id uuid, acervo text, colecao text, especialidade text, area text, tema text,
               tarefa text, pedidos bigint, aceitos bigint, primeiro timestamptz, ultimo timestamptz, publicado boolean)
language sql stable security definer set search_path = public as $$
  select u.user_id, (select a.email::text from auth.users a where a.id = u.user_id), u.materia_id,
         m.acervo, m.colecao, m.periodo, m.disciplina, m.materia, u.tarefa,
         count(*), count(*) filter (where u.ok), min(u.em), max(u.em),
         coalesce((select (r.dados->>'versao') = '4' from resumos r where r.materia_id = u.materia_id), false)
  from uso_ia u left join materias m on m.id = u.materia_id
  where u.origem in ('chave-propria', 'chave-guardada') and u.user_id is not null and u.em >= desde and (uid is null or u.user_id = uid) and eh_admin()
  group by u.user_id, u.materia_id, m.acervo, m.colecao, m.periodo, m.disciplina, m.materia, u.tarefa
  order by max(u.em) desc;
$$;
revoke all on function ajuda_contribuicoes(timestamptz, uuid) from public, anon;
grant execute on function ajuda_contribuicoes(timestamptz, uuid) to authenticated;

-- ao vivo: quem fez pedido à IA nos últimos 3 minutos (alunos, robô e o app do administrador), e em quê
create or replace function ia_ao_vivo()
returns table (user_id uuid, email text, origem text, em timestamptz, ok boolean, tarefa text, provedor text, tema text, pedidos bigint)
language sql stable security definer set search_path = public as $$
  select distinct on (u.user_id, u.origem) u.user_id, (select a.email::text from auth.users a where a.id = u.user_id), u.origem, u.em, u.ok, u.tarefa, u.provedor,
         (select m.periodo || ' › ' || m.disciplina || ' › ' || m.materia from materias m where m.id = u.materia_id),
         count(*) over (partition by u.user_id, u.origem)
  from uso_ia u where u.em >= now() - interval '3 minutes' and eh_admin()
  order by u.user_id, u.origem, u.em desc;
$$;
revoke all on function ia_ao_vivo() from public, anon;
grant execute on function ia_ao_vivo() to authenticated;
