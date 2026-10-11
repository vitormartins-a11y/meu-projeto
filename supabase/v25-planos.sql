-- v25: planos (Grátis, teste de 14 dias, Plus, VIP) e pagamento por Pix com confirmação no painel do administrador.
-- * Toda conta tem 14 dias de Plus grátis a partir do lançamento (ou de quando a conta foi criada, se for depois).
-- * Grátis: 3 usos de IA por semana (OSCE, Material de estudo ou anamnese) e 10 flashcards + 10 questões por dia.
-- * O aluno escolhe o plano, paga o Pix (o app monta o código com a sua chave) e toca em "Já paguei": ganha 48 h de
--   Plus provisório. Você confirma (ou recusa) no painel. VIP: você dá para quem quiser, com ou sem prazo.
-- * Preços e chave Pix ficam guardados aqui e você muda no painel (sem mexer no código).
-- Precisa do SQL v19 em diante. Pode rodar mais de uma vez.

-- 1) Configuração: preços (de fundador, por enquanto), chave Pix e data do lançamento
insert into config (chave, valor) values ('cobranca_inicio', now()::text) on conflict (chave) do nothing;
insert into config (chave, valor) values ('planos', '{"mensal":{"nome":"Mensal","valor":6.90,"meses":1},"semestral":{"nome":"Semestral","valor":34.90,"meses":6}}')
  on conflict (chave) do nothing;
insert into config (chave, valor) values ('pix', '{"chave":"ffca1fa2-fc11-4410-a0bb-88ea0c438590","nome":"VITOR JOSE MARTINS","cidade":"GOVERNADOR VALA"}')
  on conflict (chave) do nothing;
insert into config (chave, valor) values ('limites_gratis', '{"ia_semana":3,"flashcards_dia":10,"questoes_dia":10,"teste_dias":14}')
  on conflict (chave) do nothing;

-- 2) Tabelas
create table if not exists planos_conta (
  user_id uuid primary key references auth.users on delete cascade,
  plus_ate timestamptz,                         -- Plus pago: vale até esta data
  vip boolean not null default false,           -- VIP dado pelo administrador
  vip_ate timestamptz,                          -- VIP com prazo (vazio = sem prazo)
  obs text,
  atualizado_em timestamptz default now(),
  atualizado_por uuid);
alter table planos_conta enable row level security;
drop policy if exists meu on planos_conta;
create policy meu on planos_conta for select to authenticated using (user_id = (select auth.uid()) or (select eh_admin()));

create table if not exists pagamentos (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references auth.users on delete cascade,
  email text, nome text,
  plano text not null,
  valor numeric(10, 2) not null,
  meses int not null,
  codigo text not null unique,
  status text not null default 'aguardando' check (status in ('aguardando', 'informado', 'confirmado', 'recusado', 'cancelado')),
  pagador text,
  criado_em timestamptz not null default now(),
  informado_em timestamptz,
  decidido_em timestamptz,
  decidido_por uuid);
create index if not exists pagamentos_status on pagamentos (status, criado_em desc);
create index if not exists pagamentos_user on pagamentos (user_id, criado_em desc);
alter table pagamentos enable row level security;
drop policy if exists meus on pagamentos;
create policy meus on pagamentos for select to authenticated using (user_id = (select auth.uid()) or (select eh_admin()));

create table if not exists usos_recurso (id bigserial primary key, user_id uuid not null default auth.uid(), tipo text not null, em timestamptz not null default now());
create index if not exists usos_recurso_user on usos_recurso (user_id, em);
alter table usos_recurso enable row level security;
drop policy if exists meus on usos_recurso;
create policy meus on usos_recurso for select to authenticated using (user_id = (select auth.uid()));

alter table uso_ia add column if not exists uso text;      -- 'estudo' = ferramentas de estudo (conta no limite do Grátis)
create index if not exists uso_ia_pediu_uso on uso_ia (pediu, uso, em);

-- 3) Plano de uma conta: vip, plus, provisorio (pagou e falta confirmar, 48 h), teste (14 dias) ou gratis
create or replace function plano_de(u uuid) returns text
language sql stable security definer set search_path = public as $$
  with c as (select id, email, created_at from auth.users where id = u)
  select case
    when not exists (select 1 from c) then 'gratis'
    when exists (select 1 from c join admins a on lower(a.email) = lower(c.email)) then 'vip'
    when (select lower(email) from c) = 'robo-ia@example.com' then 'vip'
    when exists (select 1 from planos_conta p where p.user_id = u and p.vip and (p.vip_ate is null or p.vip_ate > now())) then 'vip'
    when exists (select 1 from planos_conta p where p.user_id = u and p.plus_ate > now()) then 'plus'
    when exists (select 1 from pagamentos g where g.user_id = u and g.status = 'informado' and g.informado_em > now() - interval '48 hours')
         and not exists (select 1 from pagamentos g where g.user_id = u and g.status = 'recusado') then 'provisorio'
    when greatest((select created_at from c), coalesce((select valor::timestamptz from config where chave = 'cobranca_inicio'), now()))
         + make_interval(days => coalesce(((select valor from config where chave = 'limites_gratis')::jsonb ->> 'teste_dias')::int, 14)) > now() then 'teste'
    else 'gratis' end;
$$;
revoke all on function plano_de(uuid) from public, anon, authenticated;
grant execute on function plano_de(uuid) to service_role;

-- o que o app mostra para a própria pessoa
create or replace function meu_plano() returns json
language plpgsql stable security definer set search_path = public as $$
declare u uuid := auth.uid(); lim jsonb; pl text; ini timestamptz; criado timestamptz;
begin
  if u is null then return json_build_object('plano', 'gratis'); end if;
  lim := coalesce((select valor from config where chave = 'limites_gratis')::jsonb, '{}');
  pl := plano_de(u);
  select created_at into criado from auth.users where id = u;
  ini := greatest(criado, coalesce((select valor::timestamptz from config where chave = 'cobranca_inicio'), now()));
  return json_build_object(
    'plano', pl,
    'plus_ate', (select plus_ate from planos_conta where user_id = u),
    'vip_ate', (select vip_ate from planos_conta where user_id = u and vip),
    'teste_ate', ini + make_interval(days => coalesce((lim ->> 'teste_dias')::int, 14)),
    'usos_semana', (select count(*) from usos_recurso where user_id = u and em > now() - interval '7 days'),
    'limites', lim,
    'pendente', (select row_to_json(g) from (select id, plano, valor, codigo, status, criado_em, informado_em from pagamentos
                  where user_id = u and status in ('aguardando', 'informado') order by criado_em desc limit 1) g),
    'recusado', exists (select 1 from pagamentos where user_id = u and status = 'recusado' and decidido_em > now() - interval '30 days'));
end $$;
revoke all on function meu_plano() from public, anon;
grant execute on function meu_plano() to authenticated;

-- preços e dados do Pix (para o app montar o código; a chave Pix é feita para ser divulgada)
create or replace function dados_planos() returns json
language sql stable security definer set search_path = public as $$
  select json_build_object('planos', (select valor::jsonb from config where chave = 'planos'),
                           'pix', (select valor::jsonb from config where chave = 'pix'),
                           'limites', (select valor::jsonb from config where chave = 'limites_gratis'));
$$;
revoke all on function dados_planos() from public, anon;
grant execute on function dados_planos() to authenticated;

-- 4) Um uso de IA (OSCE, Material de estudo ou anamnese novos): no Grátis, no máximo N por semana
create or replace function registrar_uso(p_tipo text) returns json
language plpgsql security definer set search_path = public as $$
declare u uuid := auth.uid(); pl text; lim int; n int;
begin
  if u is null then raise exception 'Entre na sua conta.'; end if;
  pl := plano_de(u);
  lim := coalesce(((select valor from config where chave = 'limites_gratis')::jsonb ->> 'ia_semana')::int, 3);
  select count(*) into n from usos_recurso where user_id = u and em > now() - interval '7 days';
  if pl = 'gratis' and n >= lim then return json_build_object('ok', false, 'usados', n, 'limite', lim, 'plano', pl); end if;
  insert into usos_recurso (user_id, tipo) values (u, left(coalesce(p_tipo, 'ia'), 20));
  if random() < 0.01 then delete from usos_recurso where em < now() - interval '60 days'; end if;
  return json_build_object('ok', true, 'usados', n + 1, 'limite', lim, 'plano', pl);
end $$;
revoke all on function registrar_uso(text) from public, anon;
grant execute on function registrar_uso(text) to authenticated;

-- 5) Pagamento: pedir (gera o código), informar ("Já paguei") e cancelar
create or replace function pedir_pagamento(p_plano text) returns json
language plpgsql security definer set search_path = public as $$
declare u uuid := auth.uid(); pl jsonb; cod text; g pagamentos;
begin
  if u is null then raise exception 'Entre na sua conta.'; end if;
  pl := (select valor::jsonb from config where chave = 'planos') -> p_plano;
  if pl is null then raise exception 'Plano não encontrado.'; end if;
  update pagamentos set status = 'cancelado' where user_id = u and status = 'aguardando';
  loop
    cod := 'AC' || upper(substr(replace(gen_random_uuid()::text, '-', ''), 1, 6));
    exit when not exists (select 1 from pagamentos where codigo = cod);
  end loop;
  insert into pagamentos (user_id, email, nome, plano, valor, meses, codigo)
    values (u, auth.jwt() ->> 'email', coalesce(auth.jwt() -> 'user_metadata' ->> 'nome', auth.jwt() -> 'user_metadata' ->> 'full_name'),
            p_plano, (pl ->> 'valor')::numeric, coalesce((pl ->> 'meses')::int, 1), cod)
    returning * into g;
  return json_build_object('id', g.id, 'codigo', g.codigo, 'valor', g.valor, 'plano', g.plano, 'meses', g.meses,
                           'pix', (select valor::jsonb from config where chave = 'pix'));
end $$;
create or replace function informar_pagamento(p_id uuid, p_pagador text) returns text
language plpgsql security definer set search_path = public as $$
declare u uuid := auth.uid();
begin
  update pagamentos set status = 'informado', informado_em = now(), pagador = left(trim(coalesce(p_pagador, '')), 120)
    where id = p_id and user_id = u and status = 'aguardando';
  if not found then raise exception 'Pagamento não encontrado (talvez já tenha sido informado).'; end if;
  return plano_de(u);
end $$;
create or replace function cancelar_pagamento(p_id uuid) returns void
language sql security definer set search_path = public as $$
  update pagamentos set status = 'cancelado' where id = p_id and user_id = auth.uid() and status = 'aguardando';
$$;
revoke all on function pedir_pagamento(text), informar_pagamento(uuid, text), cancelar_pagamento(uuid) from public, anon;
grant execute on function pedir_pagamento(text), informar_pagamento(uuid, text), cancelar_pagamento(uuid) to authenticated;

-- 6) Administrador: conferir pagamentos, dar e tirar VIP, mudar preços e chave Pix
create or replace function admin_pagamentos() returns setof pagamentos
language plpgsql stable security definer set search_path = public as $$
begin
  if not eh_admin() then raise exception 'Só o administrador.'; end if;
  return query select * from pagamentos
    where status in ('informado', 'aguardando') or decidido_em > now() - interval '30 days'
    order by (status = 'informado') desc, (status = 'aguardando') desc, coalesce(informado_em, criado_em) desc limit 300;
end $$;
create or replace function decidir_pagamento(p_id uuid, p_aceitar boolean) returns void
language plpgsql security definer set search_path = public as $$
declare g pagamentos; base timestamptz;
begin
  if not eh_admin() then raise exception 'Só o administrador.'; end if;
  select * into g from pagamentos where id = p_id for update;
  if g.id is null then raise exception 'Pagamento não encontrado.'; end if;
  if g.status not in ('aguardando', 'informado') then raise exception 'Este pagamento já foi decidido.'; end if;
  if p_aceitar then
    select greatest(now(), coalesce(plus_ate, now())) into base from planos_conta where user_id = g.user_id;
    insert into planos_conta (user_id, plus_ate, atualizado_por) values (g.user_id, coalesce(base, now()) + make_interval(months => g.meses), auth.uid())
      on conflict (user_id) do update set plus_ate = coalesce(base, now()) + make_interval(months => g.meses), atualizado_em = now(), atualizado_por = auth.uid();
  end if;
  update pagamentos set status = case when p_aceitar then 'confirmado' else 'recusado' end, decidido_em = now(), decidido_por = auth.uid() where id = p_id;
end $$;
create or replace function admin_planos() returns table (user_id uuid, email text, nome text, plus_ate timestamptz, vip boolean, vip_ate timestamptz, obs text)
language plpgsql stable security definer set search_path = public as $$
begin
  if not eh_admin() then raise exception 'Só o administrador.'; end if;
  return query select p.user_id, u.email::text, coalesce(u.raw_user_meta_data ->> 'nome', u.raw_user_meta_data ->> 'full_name')::text, p.plus_ate, p.vip, p.vip_ate, p.obs
    from planos_conta p join auth.users u on u.id = p.user_id
    where (p.vip and (p.vip_ate is null or p.vip_ate > now())) or p.plus_ate > now() - interval '30 days'
    order by p.vip desc, p.plus_ate desc nulls last;
end $$;
create or replace function dar_vip(p_email text, p_ate timestamptz default null, p_obs text default null) returns text
language plpgsql security definer set search_path = public as $$
declare u uuid;
begin
  if not eh_admin() then raise exception 'Só o administrador.'; end if;
  select id into u from auth.users where lower(email) = lower(trim(p_email));
  if u is null then raise exception 'Não achei conta com esse e-mail (a pessoa precisa entrar no site uma vez).'; end if;
  insert into planos_conta (user_id, vip, vip_ate, obs, atualizado_por) values (u, true, p_ate, p_obs, auth.uid())
    on conflict (user_id) do update set vip = true, vip_ate = p_ate, obs = coalesce(p_obs, planos_conta.obs), atualizado_em = now(), atualizado_por = auth.uid();
  return lower(trim(p_email));
end $$;
create or replace function tirar_vip(p_user uuid) returns void
language plpgsql security definer set search_path = public as $$
begin
  if not eh_admin() then raise exception 'Só o administrador.'; end if;
  update planos_conta set vip = false, vip_ate = null, atualizado_em = now(), atualizado_por = auth.uid() where user_id = p_user;
end $$;
create or replace function admin_salvar_planos(p_planos jsonb, p_pix jsonb, p_limites jsonb) returns void
language plpgsql security definer set search_path = public as $$
begin
  if not eh_admin() then raise exception 'Só o administrador.'; end if;
  if p_planos is not null then update config set valor = p_planos::text where chave = 'planos'; end if;
  if p_pix is not null then update config set valor = p_pix::text where chave = 'pix'; end if;
  if p_limites is not null then update config set valor = p_limites::text where chave = 'limites_gratis'; end if;
end $$;
revoke all on function admin_pagamentos(), decidir_pagamento(uuid, boolean), admin_planos(), dar_vip(text, timestamptz, text), tirar_vip(uuid),
  admin_salvar_planos(jsonb, jsonb, jsonb) from public, anon;
grant execute on function admin_pagamentos(), decidir_pagamento(uuid, boolean), admin_planos(), dar_vip(text, timestamptz, text), tirar_vip(uuid),
  admin_salvar_planos(jsonb, jsonb, jsonb) to authenticated;

select 'Pronto: planos e pagamentos. O teste grátis de 14 dias começou em ' || to_char((select valor::timestamptz from config where chave = 'cobranca_inicio'), 'DD/MM/YYYY') || '.' as resultado;
