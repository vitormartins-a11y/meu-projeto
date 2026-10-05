-- v5: arquivos que não entraram no envio e versões dos temas (rode uma vez no SQL Editor)
create table if not exists falhas_envio (
  id bigserial primary key, materia_id uuid references materias on delete cascade, nome text not null, drive_id text,
  motivo text, user_id uuid default auth.uid(), em timestamptz default now());
create index if not exists falhas_tema on falhas_envio (materia_id);
alter table falhas_envio enable row level security;
drop policy if exists ler on falhas_envio;
create policy ler on falhas_envio for select to authenticated using (eh_membro());
drop policy if exists registrar on falhas_envio;
create policy registrar on falhas_envio for insert to authenticated with check (eh_membro());
drop policy if exists limpar on falhas_envio;
create policy limpar on falhas_envio for delete to authenticated using (eh_membro());

-- Versões: a oficial é a da IA (tabela resumos); cada ajuste pedido na aba Ajustes vira uma versão nova
create table if not exists versoes (
  id uuid primary key default gen_random_uuid(), materia_id uuid not null references materias on delete cascade,
  nome text, alvo text, instrucao text, dados jsonb not null,
  autor uuid not null default auth.uid(), autor_email text default (auth.jwt() ->> 'email'), criado_em timestamptz default now());
create index if not exists versoes_tema on versoes (materia_id, criado_em);
alter table versoes enable row level security;
drop policy if exists ler on versoes;
create policy ler on versoes for select to authenticated using (eh_membro());
drop policy if exists criar on versoes;
create policy criar on versoes for insert to authenticated with check (
  eh_membro() and autor = auth.uid() and (autor_email is null or autor_email = auth.jwt() ->> 'email')
  and (eh_admin() or (select count(*) from versoes v where v.autor = auth.uid() and v.criado_em > now() - interval '1 day') < 5));
drop policy if exists apagar on versoes;
create policy apagar on versoes for delete to authenticated using (autor = auth.uid() or eh_admin());

-- Pastas pessoais ("minha prova") e anotações: cada pessoa só vê e mexe nas suas
create table if not exists pastas_pessoais (
  id uuid primary key default gen_random_uuid(), user_id uuid not null default auth.uid(),
  nome text not null, data_prova date, itens jsonb not null default '[]'::jsonb,
  criado_em timestamptz default now(), atualizado_em timestamptz default now());
create index if not exists pastas_usuario on pastas_pessoais (user_id);
alter table pastas_pessoais enable row level security;
drop policy if exists minhas on pastas_pessoais;
create policy minhas on pastas_pessoais for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
create table if not exists anotacoes (
  id uuid primary key default gen_random_uuid(), user_id uuid not null default auth.uid(),
  materia_id uuid references materias on delete cascade, aba text, x real, y real, largura real,
  texto text, cor_fundo text, cor_texto text, criado_em timestamptz default now(), atualizado_em timestamptz default now());
create index if not exists anotacoes_usuario on anotacoes (user_id, materia_id);
alter table anotacoes enable row level security;
drop policy if exists minhas on anotacoes;
create policy minhas on anotacoes for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
