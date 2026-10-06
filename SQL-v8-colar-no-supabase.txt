-- v8: Residência e Faculdade separadas, lista de temas editável e uso de IA por aluno
-- Pode rodar mais de uma vez sem problema.

-- 1) Cada tema pertence a um acervo ("residencia" ou "faculdade") e, na faculdade, a uma coleção com nome livre.
--    Tudo o que já existe vai para a Faculdade, na coleção "Primeiros envios" (o administrador pode renomear).
alter table materias add column if not exists acervo text not null default 'faculdade';
alter table materias add column if not exists colecao text not null default '';
update materias set colecao = 'Primeiros envios' where acervo = 'faculdade' and colecao = '';
-- tema criado por uma versão antiga do app (sem dizer onde) também cai nessa coleção
alter table materias alter column colecao set default 'Primeiros envios';
alter table materias drop constraint if exists materias_acervo_valido;
alter table materias add constraint materias_acervo_valido check (acervo in ('residencia', 'faculdade'));
-- o mesmo nome de tema pode existir na Residência e em cada coleção da Faculdade, sem misturar
alter table materias drop constraint if exists materias_periodo_disciplina_materia_key;
do $$ declare c text; begin   -- qualquer outra regra antiga de nome único (sem acervo e coleção) também sai
  for c in select conname from pg_constraint where conrelid = 'materias'::regclass and contype = 'u' and conname <> 'materias_lugar_unico' loop
    execute format('alter table materias drop constraint %I', c);
  end loop;
end $$;
alter table materias drop constraint if exists materias_lugar_unico;
alter table materias add constraint materias_lugar_unico unique (acervo, colecao, periodo, disciplina, materia);
create index if not exists materias_lugar on materias (acervo, colecao);

-- Renomear uma coleção da Faculdade (só o administrador)
create or replace function renomear_colecao(antigo text, novo text) returns int
language plpgsql security definer set search_path = public as $$
declare n int;
begin
  if not eh_admin() then raise exception 'Só o administrador pode renomear coleções.'; end if;
  if coalesce(trim(novo), '') = '' then raise exception 'O nome novo não pode ficar vazio.'; end if;
  update materias set colecao = trim(novo) where acervo = 'faculdade' and colecao = antigo;
  get diagnostics n = row_count; return n;
end $$;
revoke all on function renomear_colecao(text, text) from public, anon;
grant execute on function renomear_colecao(text, text) to authenticated;

-- 2) Lista oficial de temas editável pelo administrador (a turma só lê)
create table if not exists listas (
  chave text primary key, texto text not null,
  atualizado_em timestamptz default now(), atualizado_por uuid default auth.uid());
alter table listas enable row level security;
drop policy if exists ler on listas;
create policy ler on listas for select to authenticated using (eh_membro());
drop policy if exists admin_escreve on listas;
create policy admin_escreve on listas for all to authenticated using (eh_admin()) with check (eh_admin());

-- 3) Uso de IA por aluno: cada pedido anota quem pediu; cada pessoa vê só o próprio uso
alter table uso_ia add column if not exists user_id uuid;
alter table uso_ia add column if not exists chave_id text;
create index if not exists uso_ia_usuario on uso_ia (user_id, em);
drop policy if exists ler_meu on uso_ia;
create policy ler_meu on uso_ia for select to authenticated using (user_id = auth.uid());
create or replace function uso_ia_meu(desde timestamptz)
returns table (hora timestamptz, propria boolean, aceitos bigint, recusados bigint, cota_dia bigint, tokens_in bigint, tokens_out bigint)
language sql stable security definer set search_path = public as $$
  select date_trunc('hour', em), origem = 'chave-propria',
         count(*) filter (where ok), count(*) filter (where not ok),
         count(*) filter (where dia_gemini and origem = 'chave-propria'),
         coalesce(sum(tokens_in), 0), coalesce(sum(tokens_out), 0)
  from uso_ia where em >= desde and user_id = auth.uid()
  group by 1, 2 order by 1;
$$;
revoke all on function uso_ia_meu(timestamptz) from public, anon;
grant execute on function uso_ia_meu(timestamptz) to authenticated;

-- Para o administrador: a chave própria de cada aluno está funcionando? (pedidos de hoje, último pedido e modelo usado)
create or replace function uso_ia_alunos(desde timestamptz)
returns table (user_id uuid, email text, aceitos bigint, recusados bigint, cota_dia bigint,
               ultimo_em timestamptz, ultimo_ok boolean, ultimo_status int, ultimo_modelo text)
language sql stable security definer set search_path = public as $$
  select u.user_id, (select a.email::text from auth.users a where a.id = u.user_id),
         count(*) filter (where u.ok and u.em >= desde), count(*) filter (where not u.ok and u.em >= desde),
         count(*) filter (where u.dia_gemini and u.em >= desde),
         max(u.em), (array_agg(u.ok order by u.em desc))[1], (array_agg(u.status order by u.em desc))[1],
         (array_agg(u.modelo order by u.em desc) filter (where u.modelo is not null))[1]
  from uso_ia u
  where u.origem = 'chave-propria' and u.user_id is not null and u.em >= desde - interval '7 days' and eh_admin()
  group by u.user_id order by max(u.em) desc;
$$;
revoke all on function uso_ia_alunos(timestamptz) from public, anon;
grant execute on function uso_ia_alunos(timestamptz) to authenticated;
