-- v37: os temas de um estudo (material de estudo ou pasta, com a data da prova) vão para o começo da fila da IA.
-- O app anota aqui quais temas cada pessoa pediu; o robô lê e faz a apostila deles primeiro (a prova mais próxima na
-- frente). Cada pessoa vê só os pedidos dela; o robô e o administrador veem todos. Pode rodar mais de uma vez.
create table if not exists prioridade_ia (
  materia_id uuid not null references materias on delete cascade,
  user_id uuid not null default auth.uid(),
  motivo text, prazo date,
  em timestamptz not null default now(),
  primary key (materia_id, user_id));
create index if not exists prioridade_ia_em on prioridade_ia (em);
alter table prioridade_ia enable row level security;
drop policy if exists pedir on prioridade_ia;
create policy pedir on prioridade_ia for insert to authenticated
  with check (user_id = auth.uid() and materia_id = any (coalesce((select materias_visiveis()), '{}'::uuid[])));
drop policy if exists atualizar on prioridade_ia;
create policy atualizar on prioridade_ia for update to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
drop policy if exists ler on prioridade_ia;
create policy ler on prioridade_ia for select to authenticated using (user_id = auth.uid() or (select eh_admin()) or (select eh_robo()));
grant select, insert, update on prioridade_ia to authenticated;
