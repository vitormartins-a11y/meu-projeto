-- v23: segurança (precisa do SQL v19 em diante). Fecha brechas achadas na revisão de segurança:
-- * aluno não sobrescreve a apostila publicada pela IA, nem apaga as questões e os flashcards da IA;
-- * fila de envios do robô, "mudar Drive de lugar", cache da IA e contagens só valem para a turma da própria pessoa;
-- * código da turma: no máximo 8 tentativas erradas por hora por pessoa (e 100 por turma), sem prender o banco;
-- * a dona da turma só muda nome e perfil da IA pela tabela (o código e a dona só pelas funções);
-- * conta bloqueada perde também os poderes de dona;
-- * no chat e nos compartilhamentos, nome e foto vêm da conta (ninguém se passa por outra pessoa);
-- * página de um arquivo não pode ser mudada para o tema de outra turma;
-- * moderação: aluno só registra imagem como "pendente";
-- * imagens das páginas: no máximo 10 MB por arquivo.
-- Pode rodar mais de uma vez sem problema. No fim aparece um resumo do que precisa de atenção.

-- quem pode publicar/mexer no que a IA fez num tema: administrador, robô ou a dona da turma do tema
create or replace function pode_publicar(m uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select eh_admin() or eh_robo() or coalesce(eh_dono((select turma_id from materias where id = m)), false);
$$;
revoke all on function pode_publicar(uuid) from public, anon;
grant execute on function pode_publicar(uuid) to authenticated;

-- 1) Apostila/resumo do tema: depois que a IA publica (versão 4), só administrador, robô ou dona mudam
drop policy if exists enviar on resumos;
create policy enviar on resumos for insert to authenticated with check (
  materia_id = any (coalesce((select materias_visiveis()), '{}'::uuid[]))
  and (coalesce(dados ->> 'versao', '') <> '4' or pode_publicar(materia_id)));
drop policy if exists atualizar on resumos;
create policy atualizar on resumos for update to authenticated
  using (materia_id = any (coalesce((select materias_visiveis()), '{}'::uuid[])) and (coalesce(dados ->> 'versao', '') <> '4' or pode_publicar(materia_id)))
  with check (materia_id = any (coalesce((select materias_visiveis()), '{}'::uuid[])) and (coalesce(dados ->> 'versao', '') <> '4' or pode_publicar(materia_id)));

-- 2) Questões e flashcards: o que a IA fez só sai pela IA (administrador, robô, dona); o aluno apaga o que ele criou
--    e o que a leitura automática do material refaz ao enviar arquivo (questões de prova e lacunas; cards automáticos
--    de tema que a IA ainda não organizou)
drop policy if exists enviar on questoes;
create policy enviar on questoes for insert to authenticated with check (
  materia_id = any (coalesce((select materias_visiveis()), '{}'::uuid[]))
  and (origem in ('ALUNO', 'PROVA', 'LACUNA') or pode_publicar(materia_id)));
drop policy if exists apagar on questoes;
create policy apagar on questoes for delete to authenticated using (
  materia_id = any (coalesce((select materias_visiveis()), '{}'::uuid[]))
  and (criado_por = (select auth.uid()) or origem in ('PROVA', 'LACUNA') or pode_publicar(materia_id)));
drop policy if exists enviar on flashcards;
create policy enviar on flashcards for insert to authenticated with check (
  materia_id = any (coalesce((select materias_visiveis()), '{}'::uuid[]))
  and (origem = 'ALUNO' or pode_publicar(materia_id)
       or (origem = 'AUTO' and not exists (select 1 from resumos r where r.materia_id = flashcards.materia_id and r.dados ->> 'versao' = '4'))));
drop policy if exists apagar on flashcards;
create policy apagar on flashcards for delete to authenticated using (
  materia_id = any (coalesce((select materias_visiveis()), '{}'::uuid[]))
  and (criado_por = (select auth.uid()) or pode_publicar(materia_id)
       or (origem = 'AUTO' and not exists (select 1 from resumos r where r.materia_id = flashcards.materia_id and r.dados ->> 'versao' = '4'))));

-- 3) Páginas: quem enviou o arquivo altera as páginas dele, mas sem levar a página para outro tema
drop policy if exists atualizar on paginas;
create policy atualizar on paginas for update to authenticated
  using ((select eh_admin()) or exists (select 1 from documentos d where d.id = documento_id and d.criado_por = (select auth.uid())))
  with check ((select eh_admin()) or exists (select 1 from documentos d where d.id = documento_id and d.materia_id = paginas.materia_id and d.criado_por = (select auth.uid())));

-- 4) Fila de envios do robô: só para uma turma em que a pessoa está, e o pedido não aponta para outra turma
do $$ begin
  if to_regclass('public.envios_fila') is not null then
    execute 'drop policy if exists pedir on envios_fila';
    execute $p$create policy pedir on envios_fila for insert to authenticated with check (
      user_id = (select auth.uid()) and turma_id = any (coalesce((select minhas_turmas()), '{}'::uuid[]))
      and coalesce(pedido ->> 'turma_id', turma_id::text) = turma_id::text
      and coalesce(pedido -> 'escopo' ->> 'turma', turma_id::text) = turma_id::text)$p$;
    execute 'drop policy if exists mudar on envios_fila';
    execute $p$create policy mudar on envios_fila for update to authenticated
      using (eh_robo() or eh_admin() or (user_id = (select auth.uid()) and status = 'fila'))
      with check (eh_robo() or eh_admin() or (user_id = (select auth.uid()) and status in ('fila', 'cancelado')))$p$;
  end if;
end $$;
-- o robô só pega envio de quem ainda está na turma do pedido
create or replace function pegar_envio(quem text default '')
returns setof envios_fila language plpgsql security definer set search_path = public as $$
begin
  if not (eh_robo() or eh_admin()) then raise exception 'Só o robô pega envios da fila.'; end if;
  update envios_fila f set status = 'erro', erro = 'Pedido sem turma válida.', atualizado_em = now()
    where f.status = 'fila' and not exists (select 1 from turma_membros tm where tm.turma_id = f.turma_id and tm.user_id = f.user_id and tm.status = 'ativo')
      and not exists (select 1 from admins a join auth.users u on lower(u.email) = lower(a.email) where u.id = f.user_id);
  return query
  update envios_fila e set status = 'processando', robo = quem, iniciado_em = coalesce(e.iniciado_em, now()), atualizado_em = now()
  where e.id = (select f.id from envios_fila f
                where f.status = 'fila' or (f.status = 'processando' and f.atualizado_em < now() - interval '20 minutes')
                order by f.criado_em limit 1 for update skip locked)
  returning e.*;
end $$;
revoke all on function pegar_envio(text) from public, anon;
grant execute on function pegar_envio(text) to authenticated;

-- 5) Mudar Drive de lugar: só dentro da turma do tema (antes podia mexer em temas de outras turmas)
create or replace function realocar_drive(ids text[], destino_acervo text, destino_colecao text default '')
returns json language plpgsql security definer set search_path = public as $$
declare
  col text := case when destino_acervo = 'faculdade' then coalesce(nullif(trim(destino_colecao), ''), 'Sem coleção') else '' end;
  vis uuid[] := coalesce(materias_visiveis(), '{}');
  t record; alvo uuid; inteiro boolean; k int;
  n_arq int := 0; n_mov int := 0; n_jun int := 0; n_sep int := 0; temas uuid[] := '{}';
begin
  if not eh_membro() then raise exception 'Só membros da turma podem mudar arquivos de lugar.'; end if;
  if destino_acervo not in ('faculdade', 'drive', 'residencia') then raise exception 'Lugar de destino inválido.'; end if;
  if coalesce(array_length(ids, 1), 0) = 0 or not exists (
      select 1 from materias m where m.id = any(vis) and (m.acervo <> destino_acervo or m.colecao <> col)
        and (exists (select 1 from documentos d where d.materia_id = m.id and d.drive_id = any(ids))
          or exists (select 1 from midias x where x.materia_id = m.id and x.drive_id = any(ids)))) then
    return json_build_object('arquivos', 0, 'movidos', 0, 'juntados', 0, 'separados', 0, 'temas', '[]'::json);
  end if;
  -- quem não é administrador só muda de lugar os arquivos que ele mesmo enviou (e só se o tema inteiro é da turma dele)
  if not eh_admin() and (exists (
      select 1 from documentos d join materias m on m.id = d.materia_id
      where d.drive_id = any(ids) and m.id = any(vis) and (m.acervo <> destino_acervo or m.colecao <> col) and d.criado_por is distinct from auth.uid())) then
    raise exception 'Parte destes arquivos foi enviada por outra pessoa: só o administrador pode mudar de lugar.';
  end if;
  for t in
    select m.* from materias m
    where m.id = any(vis) and (m.acervo <> destino_acervo or m.colecao <> col)
      and (exists (select 1 from documentos d where d.materia_id = m.id and d.drive_id = any(ids))
        or exists (select 1 from midias x where x.materia_id = m.id and x.drive_id = any(ids)))
  loop
    inteiro := not exists (select 1 from documentos d where d.materia_id = t.id and (d.drive_id is null or not d.drive_id = any(ids)))
           and not exists (select 1 from midias x where x.materia_id = t.id and (x.drive_id is null or not x.drive_id = any(ids)));
    select count(*) into k from (
      select drive_id from documentos where materia_id = t.id and drive_id = any(ids)
      union select drive_id from midias where materia_id = t.id and drive_id = any(ids)) z;
    n_arq := n_arq + k;
    alvo := null;
    select id into alvo from materias
      where turma_id is not distinct from t.turma_id and acervo = destino_acervo and colecao = col
        and periodo = t.periodo and disciplina = t.disciplina and materia = t.materia;
    if inteiro and alvo is null then
      update materias set acervo = destino_acervo, colecao = col where id = t.id;
      n_mov := n_mov + 1; temas := temas || t.id; continue;
    end if;
    if alvo is null then
      insert into materias (turma_id, periodo, disciplina, materia, acervo, colecao)
        values (t.turma_id, t.periodo, t.disciplina, t.materia, destino_acervo, col) returning id into alvo;
    end if;
    update paginas set materia_id = alvo where documento_id in (select id from documentos where materia_id = t.id and drive_id = any(ids));
    update documentos set materia_id = alvo where materia_id = t.id and drive_id = any(ids);
    update midias set materia_id = alvo where materia_id = t.id and drive_id = any(ids);
    begin
      update falhas_envio set materia_id = alvo where materia_id = t.id and drive_id = any(ids);
    exception when undefined_table or undefined_column then null;
    end;
    if inteiro then
      update flashcards set materia_id = alvo where materia_id = t.id and origem = 'ALUNO';
      update questoes set materia_id = alvo where materia_id = t.id and origem = 'ALUNO';
      delete from materias where id = t.id;
      n_jun := n_jun + 1;
    else
      delete from resumos where materia_id = t.id;
      delete from flashcards where materia_id = t.id and origem <> 'ALUNO';
      delete from questoes where materia_id = t.id and origem <> 'ALUNO';
      n_sep := n_sep + 1;
    end if;
    temas := temas || alvo;
  end loop;
  return json_build_object('arquivos', n_arq, 'movidos', n_mov, 'juntados', n_jun, 'separados', n_sep,
    'temas', (select coalesce(json_agg(distinct x), '[]'::json) from unnest(temas) x));
end $$;
revoke all on function realocar_drive(text[], text, text) from public, anon;
grant execute on function realocar_drive(text[], text, text) to authenticated;

-- 6) Contagem de questões/flashcards por tema: só dos temas que a pessoa vê
create or replace function contar_por_tema(tabela text)
returns table (materia_id uuid, n bigint) language plpgsql stable security definer set search_path = public as $$
declare vis uuid[] := coalesce(materias_visiveis(), '{}');
begin
  if tabela = 'questoes' then return query select q.materia_id, count(*) from questoes q where q.materia_id = any(vis) group by q.materia_id;
  elsif tabela = 'flashcards' then return query select f.materia_id, count(*) from flashcards f where f.materia_id = any(vis) group by f.materia_id;
  end if;
end $$;
revoke all on function contar_por_tema(text) from public, anon;
grant execute on function contar_por_tema(text) to authenticated;

-- 7) Cache da IA (casos de OSCE, setinhas, revisão rápida): cada chave tem o tema no meio ("osce:<tema>:..."),
--    e só quem vê o tema lê ou grava. As marcas de revisão do texto ("rev:") só o robô e o administrador gravam.
create or replace function cache_do_meu_tema(chave text) returns boolean
language sql stable security definer set search_path = public as $$
  select eh_admin() or eh_robo() or (
    split_part(chave, ':', 1) <> 'rev'
    and split_part(chave, ':', 2) ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
    and split_part(chave, ':', 2)::uuid = any (coalesce(materias_visiveis(), '{}')));
$$;
revoke all on function cache_do_meu_tema(text) from public, anon;
grant execute on function cache_do_meu_tema(text) to authenticated;
do $$ begin
  if to_regclass('public.cache_ia') is not null then
    execute 'drop policy if exists ler on cache_ia';
    execute 'create policy ler on cache_ia for select to authenticated using (cache_do_meu_tema(chave))';
    execute 'drop policy if exists criar on cache_ia';
    execute 'create policy criar on cache_ia for insert to authenticated with check (cache_do_meu_tema(chave))';
    execute 'drop policy if exists mudar on cache_ia';
    execute 'create policy mudar on cache_ia for update to authenticated using (cache_do_meu_tema(chave)) with check (cache_do_meu_tema(chave))';
  end if;
end $$;

-- 8) Código da turma: tentativas contadas (sem o pg_sleep, que prendia conexões do banco)
create table if not exists tentativas_codigo (user_id uuid, turma_id uuid, em timestamptz not null default now());
create index if not exists tentativas_codigo_user on tentativas_codigo (user_id, em);
create index if not exists tentativas_codigo_turma on tentativas_codigo (turma_id, em);
alter table tentativas_codigo enable row level security;     -- ninguém lê nem grava direto (só a função)
create or replace function entrar_turma(t uuid, codigo text) returns boolean
language plpgsql security definer set search_path = public as $$
declare certo text;
begin
  if auth.uid() is null or exists (select 1 from bloqueados where user_id = auth.uid()) then return false; end if;
  if (select count(*) from tentativas_codigo where user_id = auth.uid() and em > now() - interval '1 hour') >= 8
     or (select count(*) from tentativas_codigo where turma_id = t and em > now() - interval '1 hour') >= 100 then
    raise exception 'Muitas tentativas com código errado. Espere uma hora ou peça para entrar.';
  end if;
  select turmas.codigo into certo from turmas where id = t;
  if certo is not null and upper(trim(coalesce(codigo, ''))) = upper(trim(certo)) then
    insert into turma_membros (turma_id, user_id, email, nome, status)
      values (t, auth.uid(), auth.jwt() ->> 'email', auth.jwt() -> 'user_metadata' ->> 'full_name', 'ativo')
      on conflict (turma_id, user_id) do update set status = 'ativo';
    return true;
  end if;
  insert into tentativas_codigo (user_id, turma_id) values (auth.uid(), t);
  if random() < 0.02 then delete from tentativas_codigo where em < now() - interval '1 day'; end if;
  return false;
end $$;
revoke all on function entrar_turma(uuid, text) from public, anon;
grant execute on function entrar_turma(uuid, text) to authenticated;
-- código novo sorteado de verdade (8 letras/números); escolhido pela dona: pelo menos 6
alter table turmas alter column codigo set default upper(substr(replace(gen_random_uuid()::text, '-', ''), 1, 8));
create or replace function trocar_codigo(t uuid, novo text) returns text
language plpgsql security definer set search_path = public as $$
declare c text := upper(regexp_replace(coalesce(novo, ''), '\s', '', 'g'));
begin
  if not eh_dono(t) then raise exception 'Só a dona da turma muda o código.'; end if;
  if length(c) < 6 then c := upper(substr(replace(gen_random_uuid()::text, '-', ''), 1, 8)); end if;
  update turmas set codigo = c where id = t;
  if t = turma_padrao() then update config set valor = c where chave = 'codigo_turma'; end if;
  return c;
end $$;
revoke all on function trocar_codigo(uuid, text) from public, anon;
grant execute on function trocar_codigo(uuid, text) to authenticated;
-- o código de exemplo que aparece no código do site não pode continuar valendo
do $$ declare c text := upper(substr(replace(gen_random_uuid()::text, '-', ''), 1, 8)); begin
  if exists (select 1 from turmas where upper(codigo) = 'TROQUE-ESTE-CODIGO') then
    update turmas set codigo = c where upper(codigo) = 'TROQUE-ESTE-CODIGO';
    update config set valor = c where chave = 'codigo_turma' and upper(valor) = 'TROQUE-ESTE-CODIGO';
    raise notice 'O código da turma ainda era o de exemplo e foi trocado. Veja o novo em Administração > Cursos e turmas.';
  end if;
end $$;

-- 9) Turma: pela tabela, a dona só muda nome e perfil da IA (dona e código só pelas funções)
revoke update on turmas from anon, authenticated;
grant update (nome, perfil_ia) on turmas to authenticated;
-- conta bloqueada não tem poder de dona
create or replace function eh_dono(t uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select eh_admin() or (not exists (select 1 from bloqueados where user_id = auth.uid()) and (
    exists (select 1 from turmas where id = t and dono = auth.uid())
    or exists (select 1 from turma_membros where turma_id = t and user_id = auth.uid() and papel = 'dono' and status = 'ativo')));
$$;

-- 10) Chat e compartilhamentos: nome e foto vêm da conta de quem manda
create or replace function nome_foto_da_conta() returns trigger
language plpgsql security definer set search_path = public as $$
declare md jsonb; em text; f text;
begin
  if auth.uid() is null then return new; end if;                 -- servidor (chave de serviço): como veio
  select raw_user_meta_data, email into md, em from auth.users where id = auth.uid();
  md := coalesce(md, '{}');
  if tg_table_name = 'mensagens' then
    new.nome := left(coalesce(nullif(md ->> 'nome', ''), nullif(md ->> 'full_name', ''), nullif(md ->> 'name', ''), split_part(em, '@', 1), 'Alguém'), 60);
    f := coalesce(nullif(md ->> 'foto', ''), nullif(md ->> 'avatar_url', ''), nullif(md ->> 'picture', ''));
    -- só foto guardada no próprio site ou a foto da conta Google (endereço de fora poderia rastrear quem abre o chat)
    new.foto := case when f ~ '^https://[a-z0-9-]+\.supabase\.co/storage/v1/object/public/avatares/' or f ~ '^https://[a-z0-9-]+\.googleusercontent\.com/' then f end;
    if new.tipo = 'evento' then new.nome := null; end if;
  elsif tg_table_name = 'compartilhados' then
    new.de_nome := left(coalesce(nullif(md ->> 'nome', ''), nullif(md ->> 'full_name', ''), nullif(md ->> 'name', ''), split_part(em, '@', 1), 'Alguém'), 60);
  end if;
  return new;
end $$;
do $$ begin
  if to_regclass('public.mensagens') is not null then
    execute 'drop trigger if exists nome_foto on mensagens';
    execute 'create trigger nome_foto before insert on mensagens for each row execute function nome_foto_da_conta()';
  end if;
  if to_regclass('public.compartilhados') is not null then
    execute 'drop trigger if exists nome_foto on compartilhados';
    execute 'create trigger nome_foto before insert on compartilhados for each row execute function nome_foto_da_conta()';
  end if;
end $$;

-- 11) Moderação de imagens: aluno só registra como "pendente" (liberar ou remover é do administrador)
drop policy if exists registrar on moderacao;
create policy registrar on moderacao for insert to authenticated with check (
  (select eh_membro()) and user_id = (select auth.uid()) and (status = 'pendente' or (select eh_admin())));

-- 12) Votos: só nas questões que a pessoa vê, e não dá para mudar o voto de questão
do $$ begin
  execute 'drop policy if exists ler on votos';
  execute $p$create policy ler on votos for select to authenticated using (exists (select 1 from questoes q where q.id = questao_id))$p$;
  execute 'drop policy if exists votar on votos';
  execute $p$create policy votar on votos for insert to authenticated with check (user_id = (select auth.uid()) and exists (select 1 from questoes q where q.id = questao_id))$p$;
  execute 'drop policy if exists mudar_voto on votos';
  execute $p$create policy mudar_voto on votos for update to authenticated using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()) and exists (select 1 from questoes q where q.id = questao_id))$p$;
end $$;

-- 13) Listas de temas: cada turma lê a sua (e a lista geral)
do $$ begin
  if to_regclass('public.listas') is not null then
    execute 'drop policy if exists ler on listas';
    execute $p$create policy ler on listas for select to authenticated using (
      (select eh_admin()) or chave not like 'temas:%'
      or (split_part(chave, ':', 2) ~* '^[0-9a-f-]{36}$' and split_part(chave, ':', 2)::uuid = any (coalesce((select minhas_turmas()), '{}'::uuid[]))))$p$;
  end if;
end $$;

-- 14) Imagens das páginas: no máximo 10 MB por arquivo
do $$ begin
  update storage.buckets set file_size_limit = 10485760 where id = 'paginas';
exception when undefined_column then null; end $$;

-- 15) "midias" (áudios e vídeos na fila de transcrição): se a tabela estiver sem proteção, protege
do $$ begin
  if to_regclass('public.midias') is not null and not (select relrowsecurity from pg_class where oid = 'public.midias'::regclass) then
    execute 'alter table midias enable row level security';
    execute 'drop policy if exists ler on midias';
    execute $p$create policy ler on midias for select to authenticated using (materia_id = any (coalesce((select materias_visiveis()), '{}'::uuid[])))$p$;
    execute 'drop policy if exists enviar on midias';
    execute $p$create policy enviar on midias for insert to authenticated with check (materia_id = any (coalesce((select materias_visiveis()), '{}'::uuid[])))$p$;
    raise notice 'A tabela midias estava sem proteção e foi protegida.';
  end if;
end $$;

-- 16) Funções que não precisam ficar abertas para quem nem entrou na conta
do $$ begin
  revoke execute on function eh_membro() from public, anon;
  revoke execute on function eh_robo() from public, anon;
  revoke execute on function turma_padrao() from public, anon;
  grant execute on function eh_membro(), eh_robo(), turma_padrao() to authenticated;
exception when undefined_function then null; end $$;

-- Resumo: o que ainda precisa de atenção (se aparecer "tudo certo", não precisa fazer nada)
select coalesce(string_agg(x, ' | '), 'Pronto: segurança atualizada, tudo certo.') as resultado from (
  select 'Tabela sem proteção (RLS desligado): ' || c.relname as x
    from pg_class c join pg_namespace n on n.oid = c.relnamespace
    where n.nspname = 'public' and c.relkind = 'r' and not c.relrowsecurity
  union all
  select 'Regra antiga ainda usando eh_membro em ' || tablename || '.' || policyname
    from pg_policies where schemaname = 'public' and (qual ~ 'eh_membro\(\)' or with_check ~ 'eh_membro\(\)')
      and tablename not in ('moderacao', 'cursos', 'turmas', 'turma_membros', 'envios_fila', 'reportes', 'meus_estudos')) z;
