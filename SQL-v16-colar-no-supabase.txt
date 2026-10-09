-- v16: reaproveitar o que a IA já fez (gasta menos cota)
-- Os casos de OSCE de cada tema e as "setinhas" dos complementos do material de estudo vêm só do conteúdo do acervo
-- (nada pessoal). Ficam guardados aqui e o próximo colega que pedir o mesmo tema recebe na hora, sem gastar IA.
-- Quando o tema é publicado de novo, a chave muda e a IA faz outra vez. Pode rodar mais de uma vez sem problema.
create table if not exists cache_ia (
  chave text primary key,
  dados jsonb not null,
  criado_em timestamptz default now(),
  atualizado_em timestamptz default now());
alter table cache_ia enable row level security;
drop policy if exists ler on cache_ia;
create policy ler on cache_ia for select to authenticated using (eh_membro());
drop policy if exists criar on cache_ia;
create policy criar on cache_ia for insert to authenticated with check (eh_membro());
drop policy if exists mudar on cache_ia;
create policy mudar on cache_ia for update to authenticated using (eh_membro()) with check (eh_membro());
drop policy if exists apagar on cache_ia;
create policy apagar on cache_ia for delete to authenticated using (eh_admin());
