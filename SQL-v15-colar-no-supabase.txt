-- v15: Anamneses e OSCE (guardados só para a própria pessoa) e envio do Drive pelo robô (fila de envios)
-- Pode rodar mais de uma vez sem problema.

-- 1) Anamneses e OSCE de cada pessoa. Só a dona vê, cria, muda e apaga (nem o administrador vê).
create table if not exists meus_estudos (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid(),
  tipo text not null check (tipo in ('caso', 'osce')),
  titulo text not null default '',
  dados jsonb not null default '{}'::jsonb,
  criado_em timestamptz default now(),
  atualizado_em timestamptz default now());
create index if not exists meus_estudos_usuario on meus_estudos (user_id, tipo, atualizado_em desc);
alter table meus_estudos enable row level security;
drop policy if exists meus on meus_estudos;
create policy meus on meus_estudos for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid() and eh_membro());

-- 2) Fila de envios: a pessoa deixa o link do Drive e pode fechar o site; o robô do computador faz o envio.
create or replace function eh_robo() returns boolean
language sql stable security definer set search_path = public as $$
  select lower(coalesce(auth.jwt() ->> 'email', '')) = 'robo-ia@example.com';
$$;
create table if not exists envios_fila (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid(),
  email text,
  pedido jsonb not null,                    -- link, pasta, lugar (Faculdade/Drive/Residência), organização
  status text not null default 'fila' check (status in ('fila', 'processando', 'pronto', 'erro', 'cancelado')),
  progresso jsonb,                          -- arquivo atual, quantos já foram, últimas mensagens
  resultado jsonb,
  erro text,
  robo text,
  criado_em timestamptz default now(),
  iniciado_em timestamptz,
  atualizado_em timestamptz default now(),
  terminado_em timestamptz);
create index if not exists envios_fila_status on envios_fila (status, criado_em);
alter table envios_fila enable row level security;
drop policy if exists pedir on envios_fila;
drop policy if exists ver on envios_fila;
drop policy if exists mudar on envios_fila;
drop policy if exists apagar on envios_fila;
create policy pedir on envios_fila for insert to authenticated with check (user_id = auth.uid() and eh_membro());
create policy ver on envios_fila for select to authenticated using (user_id = auth.uid() or eh_admin() or eh_robo());
create policy mudar on envios_fila for update to authenticated using (eh_robo() or eh_admin() or (user_id = auth.uid() and status = 'fila'));
create policy apagar on envios_fila for delete to authenticated using (eh_admin() or (user_id = auth.uid() and status <> 'processando'));

-- o robô reserva o próximo envio (dois robôs nunca pegam o mesmo). Um envio "processando" sem notícia há 20 minutos
-- (computador desligado no meio) volta a ser pego e continua: o que já tinha sido enviado é pulado.
create or replace function pegar_envio(quem text default '')
returns setof envios_fila language plpgsql security definer set search_path = public as $$
begin
  if not (eh_robo() or eh_admin()) then raise exception 'Só o robô pega envios da fila.'; end if;
  return query
  update envios_fila e set status = 'processando', robo = quem, iniciado_em = coalesce(e.iniciado_em, now()), atualizado_em = now()
  where e.id = (select f.id from envios_fila f
                where f.status = 'fila' or (f.status = 'processando' and f.atualizado_em < now() - interval '20 minutes')
                order by f.criado_em limit 1 for update skip locked)
  returning e.*;
end $$;
revoke all on function pegar_envio(text) from public, anon;
grant execute on function pegar_envio(text) to authenticated;
