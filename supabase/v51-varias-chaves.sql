-- v51: cada conta pode deixar VÁRIAS chaves de IA para a turma, do Gemini e do Groq.
-- As chaves ficam cifradas; só a função "ia" (chave de serviço) lê. O site nunca vê a chave: a pessoa vê as dela (final,
-- situação, o que fizeram) e o administrador vê todas. As chaves do Gemini já guardadas (v12) passam para a tabela nova.
-- Pode rodar mais de uma vez.

create table if not exists chaves_api (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users on delete cascade,
  provedor text not null check (provedor in ('gemini', 'groq')),
  cifrada text not null,
  final text,                         -- 4 últimos caracteres, só para a pessoa reconhecer a chave
  chave_id text not null,             -- resumo (hash) curto da chave: a mesma chave não entra duas vezes
  ativa boolean not null default true,
  recusada_em timestamptz,            -- o Google/Groq recusou a chave (apagada ou copiada errada)
  descanso_ate timestamptz,           -- sem cota até esta hora
  ultimo_uso timestamptz,
  ultimo_ok boolean,                  -- o último pedido com ela deu certo?
  ultima_tarefa text,                 -- o que ela fez por último (apostila, questões, resumo, voz…)
  ultimo_erro text,                   -- o último erro (cota do dia, cota do minuto, recusada, demorou…)
  usos int not null default 0,        -- pedidos que deram certo com ela
  falhas int not null default 0,      -- pedidos que não deram
  criado_em timestamptz default now(),
  unique (chave_id));
create index if not exists chaves_api_prov on chaves_api (provedor, ativa);
create index if not exists chaves_api_dono on chaves_api (user_id);
alter table chaves_api enable row level security;   -- sem nenhuma regra de acesso: só a função "ia" lê a tabela
revoke all on chaves_api from anon, authenticated;

-- as chaves do Gemini que já estavam guardadas (uma por pessoa, v12) passam para a tabela nova
do $$ begin
  if to_regclass('public.chaves_ia') is not null then
    insert into chaves_api (user_id, provedor, cifrada, final, chave_id, ativa, recusada_em, descanso_ate, ultimo_uso, criado_em)
    select user_id, 'gemini', cifrada, final, coalesce(chave_id, left(md5(cifrada), 10)), ativa, recusada_em, descanso_ate, ultimo_uso, criado_em
    from chaves_ia
    on conflict (chave_id) do nothing;
  end if;
end $$;

-- 10% das chaves do Gemini (no mínimo 1) ficam de reserva para as ferramentas de estudo (como na v17): o robô não usa
create or replace function chaves_reserva_api() returns uuid[]
language sql stable security definer set search_path = public as $$
  with boas as (select id from chaves_api where provedor = 'gemini' and ativa and recusada_em is null)
  select coalesce(array_agg(id), '{}') from (
    select id from boas order by id
    limit (select greatest(1, ceil(count(*) * 0.10))::int from boas)) r;
$$;
revoke all on function chaves_reserva_api() from public, anon, authenticated;
grant execute on function chaves_reserva_api() to service_role;

-- a função "ia" pega a chave que está há mais tempo sem uso (duas chamadas ao mesmo tempo nunca pegam a mesma).
-- Gemini: 'estudo' (alunos) só a reserva; 'fila' (robô) usa a reserva por último. Groq: todas.
create or replace function pegar_chave_api(prov text, evitar uuid[] default '{}', modo text default 'fila')
returns table (id uuid, user_id uuid, cifrada text, chave_id text, reserva boolean)
language plpgsql security definer set search_path = public as $$
declare res uuid[] := case when prov = 'gemini' then chaves_reserva_api() else '{}'::uuid[] end;
begin
  return query
  update chaves_api c set ultimo_uso = now()
  where c.id = (select k.id from chaves_api k
                where k.provedor = prov and k.ativa and k.recusada_em is null and coalesce(k.descanso_ate, '-infinity') < now()
                  and not (k.id = any(evitar))
                  and (prov <> 'gemini' or modo = 'fila' or k.id = any(res))
                -- (a fila usa primeiro as chaves de fora da reserva; a reserva só quando não sobra nenhuma — como na v36)
                order by (k.id = any(res)), k.ultimo_uso nulls first
                limit 1 for update skip locked)
  returning c.id, c.user_id, c.cifrada, c.chave_id, c.id = any(res);
end $$;
revoke all on function pegar_chave_api(text, uuid[], text) from public, anon, authenticated;
grant execute on function pegar_chave_api(text, uuid[], text) to service_role;

-- depois de cada pedido, a função "ia" anota o resultado na chave (o que ela fez, se deu certo, o erro)
create or replace function anotar_chave_api(k_id uuid, ok boolean, tarefa text, erro text)
returns void language sql security definer set search_path = public as $$
  update chaves_api set ultimo_ok = ok, ultima_tarefa = left(tarefa, 40), ultimo_erro = case when ok then null else left(erro, 160) end,
    usos = usos + case when ok then 1 else 0 end, falhas = falhas + case when ok then 0 else 1 end
  where id = k_id;
$$;
revoke all on function anotar_chave_api(uuid, boolean, text, text) from public, anon, authenticated;
grant execute on function anotar_chave_api(uuid, boolean, text, text) to service_role;

-- as chaves da própria pessoa (nunca a chave): situação e o que fizeram nas últimas 24 horas
create or replace function minhas_chaves()
returns table (id uuid, provedor text, final text, ativa boolean, recusada_em timestamptz, descanso_ate timestamptz, ultimo_uso timestamptz,
               ultimo_ok boolean, ultima_tarefa text, ultimo_erro text, usos int, falhas int, criado_em timestamptz,
               ok_24h bigint, falhas_24h bigint, reserva boolean)
language sql stable security definer set search_path = public as $$
  select k.id, k.provedor, k.final, k.ativa, k.recusada_em, k.descanso_ate, k.ultimo_uso, k.ultimo_ok, k.ultima_tarefa, k.ultimo_erro,
         k.usos, k.falhas, k.criado_em,
         (select count(*) from uso_ia u where u.chave_id = k.chave_id and u.ok and u.em > now() - interval '24 hours'),
         (select count(*) from uso_ia u where u.chave_id = k.chave_id and not u.ok and u.em > now() - interval '24 hours'),
         k.id = any(chaves_reserva_api())
  from chaves_api k where k.user_id = auth.uid() order by k.provedor, k.criado_em;
$$;
revoke all on function minhas_chaves() from public, anon;
grant execute on function minhas_chaves() to authenticated;

-- todas as chaves da turma (só o administrador): de quem é, situação e o que fizeram nas últimas 24 horas
create or replace function chaves_turma()
returns table (id uuid, user_id uuid, email text, provedor text, final text, ativa boolean, recusada_em timestamptz, descanso_ate timestamptz,
               ultimo_uso timestamptz, ultimo_ok boolean, ultima_tarefa text, ultimo_erro text, usos int, falhas int, criado_em timestamptz,
               ok_24h bigint, falhas_24h bigint, reserva boolean)
language sql stable security definer set search_path = public as $$
  select k.id, k.user_id, (select a.email::text from auth.users a where a.id = k.user_id), k.provedor, k.final, k.ativa, k.recusada_em, k.descanso_ate,
         k.ultimo_uso, k.ultimo_ok, k.ultima_tarefa, k.ultimo_erro, k.usos, k.falhas, k.criado_em,
         (select count(*) from uso_ia u where u.chave_id = k.chave_id and u.ok and u.em > now() - interval '24 hours'),
         (select count(*) from uso_ia u where u.chave_id = k.chave_id and not u.ok and u.em > now() - interval '24 hours'),
         k.id = any(chaves_reserva_api())
  from chaves_api k where eh_admin() order by k.provedor, k.ultimo_uso desc nulls last;
$$;
revoke all on function chaves_turma() from public, anon;
grant execute on function chaves_turma() to authenticated;

-- o que já existia passa a olhar a tabela nova (o robô decide quantos temas faz de uma vez por aqui)
create or replace function chaves_guardadas_disponiveis() returns int
language sql stable security definer set search_path = public as $$
  select case when eh_membro() then (select count(*)::int from chaves_api where provedor = 'gemini' and ativa and recusada_em is null
    and coalesce(descanso_ate, '-infinity') < now() and not (id = any(chaves_reserva_api()))) else 0 end;
$$;
revoke all on function chaves_guardadas_disponiveis() from public, anon;
grant execute on function chaves_guardadas_disponiveis() to authenticated;

create or replace function minha_chave_guardada()
returns table (final text, ativa boolean, recusada_em timestamptz, descanso_ate timestamptz, ultimo_uso timestamptz, criado_em timestamptz)
language sql stable security definer set search_path = public as $$
  select final, ativa, recusada_em, descanso_ate, ultimo_uso, criado_em from chaves_api
  where user_id = auth.uid() and provedor = 'gemini' order by ativa desc, criado_em desc limit 1;
$$;
revoke all on function minha_chave_guardada() from public, anon;
grant execute on function minha_chave_guardada() to authenticated;

create or replace function ajudantes(desde timestamptz)
returns table (user_id uuid, email text, guardada boolean, guardada_ativa boolean, recusada_em timestamptz, descanso_ate timestamptz,
               aceitos bigint, recusados bigint, cota_dia bigint, chave_recusada bigint, ultimo_em timestamptz, ultimo_ok boolean,
               ultima_origem text, ultima_tarefa text, ultimo_tema text, temas bigint)
language sql stable security definer set search_path = public as $$
  with gente as (
    select k.user_id from chaves_api k
    union select u.user_id from uso_ia u where u.origem in ('chave-propria', 'chave-guardada') and u.user_id is not null and u.em >= now() - interval '30 days'),
  ch as (
    select k.user_id, bool_or(k.ativa) ativa, max(k.recusada_em) recusada_em, min(k.descanso_ate) descanso_ate
    from chaves_api k group by k.user_id),
  hoje as (
    select u.user_id, count(*) filter (where u.ok) a, count(*) filter (where not u.ok) r,
           count(*) filter (where u.dia_gemini or u.dia_groq) c, count(*) filter (where not u.ok and u.status in (401, 502)) cr,
           count(distinct u.materia_id) t
    from uso_ia u where u.origem in ('chave-propria', 'chave-guardada') and u.em >= desde group by u.user_id),
  ultimo as (
    select distinct on (u.user_id) u.user_id, u.em, u.ok, u.origem, u.tarefa, u.materia_id
    from uso_ia u where u.origem in ('chave-propria', 'chave-guardada') and u.user_id is not null order by u.user_id, u.em desc)
  select g.user_id, (select a.email::text from auth.users a where a.id = g.user_id),
         ch.user_id is not null, coalesce(ch.ativa, false), ch.recusada_em, ch.descanso_ate,
         coalesce(h.a, 0), coalesce(h.r, 0), coalesce(h.c, 0), coalesce(h.cr, 0),
         l.em, l.ok, l.origem, l.tarefa, (select m.periodo || ' › ' || m.disciplina || ' › ' || m.materia from materias m where m.id = l.materia_id),
         coalesce(h.t, 0)
  from gente g left join ch on ch.user_id = g.user_id left join hoje h on h.user_id = g.user_id left join ultimo l on l.user_id = g.user_id
  where eh_admin() order by l.em desc nulls last;
$$;
revoke all on function ajudantes(timestamptz) from public, anon;
grant execute on function ajudantes(timestamptz) to authenticated;

select 'v51 pronto' as resultado;
