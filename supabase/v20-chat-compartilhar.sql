-- v20: chat da turma e compartilhamento por link (precisa do SQL v19)
-- * Chat: cada turma tem o seu. Mostra nome e foto de quem mandou. Avisos automáticos ("Fulano enviou 3 arquivos",
--   "Tema X foi publicado"). Apaga a própria mensagem; a dona da turma e o administrador apagam qualquer uma.
--   Mensagens com mais de 1 ano são apagadas sozinhas, para não encher o banco grátis.
-- * Compartilhar: OSCE, caso de anamnese ou material de estudo viram um link. Quem abre ganha uma cópia na pasta dele,
--   marcada "Compartilhado por Fulano". Ninguém consegue listar os compartilhamentos: só abre quem tem o link.
-- Pode rodar mais de uma vez sem problema.

create table if not exists mensagens (
  id bigserial primary key,
  turma_id uuid not null references turmas on delete cascade,
  user_id uuid default auth.uid(),
  nome text, foto text,
  texto text not null check (length(texto) between 1 and 2000),
  tipo text not null default 'msg' check (tipo in ('msg', 'evento')),
  criado_em timestamptz not null default now());
create index if not exists mensagens_turma on mensagens (turma_id, id desc);
grant select, insert, delete on mensagens to authenticated;
grant usage, select on sequence mensagens_id_seq to authenticated;
alter table mensagens enable row level security;
drop policy if exists ler on mensagens;
create policy ler on mensagens for select to authenticated using (turma_id = any (coalesce((select minhas_turmas()), '{}'::uuid[])));
drop policy if exists mandar on mensagens;
create policy mandar on mensagens for insert to authenticated
  with check (tipo = 'msg' and user_id = (select auth.uid()) and turma_id = any (coalesce((select minhas_turmas()), '{}'::uuid[])));
drop policy if exists apagar on mensagens;
create policy apagar on mensagens for delete to authenticated using (user_id = (select auth.uid()) or eh_dono(turma_id));
-- aviso automático (envio de arquivos, tema publicado): só por esta função
create or replace function aviso_turma(t uuid, p_texto text) returns void
language plpgsql security definer set search_path = public as $$
begin
  if not (t = any (minhas_turmas())) then return; end if;
  insert into mensagens (turma_id, user_id, nome, texto, tipo) values (t, auth.uid(), null, left(p_texto, 500), 'evento');
  if random() < 0.01 then delete from mensagens where criado_em < now() - interval '1 year'; end if;
end $$;
revoke all on function aviso_turma(uuid, text) from public, anon;
grant execute on function aviso_turma(uuid, text) to authenticated;
-- chat ao vivo (sem ficar perguntando ao banco de tempos em tempos)
do $$ begin
  if exists (select 1 from pg_publication where pubname = 'supabase_realtime')
     and not exists (select 1 from pg_publication_tables where pubname = 'supabase_realtime' and tablename = 'mensagens') then
    execute 'alter publication supabase_realtime add table mensagens';
  end if;
end $$;

create table if not exists compartilhados (
  id uuid primary key default gen_random_uuid(),
  tipo text not null check (tipo in ('osce', 'caso', 'material')),
  titulo text not null default '',
  dados jsonb not null,
  de_user uuid not null default auth.uid(),
  de_nome text,
  criado_em timestamptz default now());
alter table compartilhados enable row level security;
drop policy if exists meus on compartilhados;
create policy meus on compartilhados for all to authenticated using (de_user = (select auth.uid())) with check (de_user = (select auth.uid()));
-- abrir pelo link (o id é longo e aleatório): devolve um compartilhamento, sem deixar listar os outros
create or replace function abrir_compartilhado(c uuid) returns table (id uuid, tipo text, titulo text, dados jsonb, de_nome text, criado_em timestamptz)
language sql stable security definer set search_path = public as $$
  select id, tipo, titulo, dados, de_nome, criado_em from compartilhados where id = c and auth.uid() is not null;
$$;
revoke all on function abrir_compartilhado(uuid) from public, anon;
grant execute on function abrir_compartilhado(uuid) to authenticated;

select 'Pronto: chat e compartilhamento. ' || case when exists (select 1 from pg_publication_tables where pubname = 'supabase_realtime' and tablename = 'mensagens')
  then 'Chat ao vivo ligado.' else 'Chat sem o modo ao vivo (atualiza a cada 15 segundos).' end as resultado;
