-- v27: organização pela turma, figuras conferidas pela IA, cópias e limpeza das imagens. Precisa do v26. Pode rodar mais de uma vez.
-- * Abas da biblioteca: cada turma renomeia as abas e cria outras (turmas.abas). Qualquer pessoa da turma.
-- * Qualquer pessoa da turma: muda um arquivo de tema, renomeia especialidade e área, e edita a lista de temas da turma.
-- * Figuras: o robô marca cada PDF depois que a IA conferiu as figuras (figuras_rev); os antigos entram na fila dele.
-- * Cópias: cada arquivo guarda a "impressão digital" do texto (texto_hash); a mesma apostila com outro nome não entra 2 vezes.
-- * Limpeza: lista as imagens do Storage que nenhuma página usa mais (o robô apaga as com mais de 2 dias).

-- 1) Cópias: impressão digital do texto (a mesma conta do app: sem acentos, só letras e números, páginas separadas por "|")
alter table documentos add column if not exists texto_hash text;
create index if not exists documentos_texto_hash on documentos (texto_hash) where texto_hash is not null;
with t as (
  select p.documento_id,
         string_agg(regexp_replace(translate(lower(translate(regexp_replace(coalesce(p.texto, ''), '\[\[FIG:[0-9]+\]\]', '', 'g'),
           'ÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇÑ', 'áàâãäéèêëíìîïóòôõöúùûüçñ')), 'áàâãäéèêëíìîïóòôõöúùûüçñ', 'aaaaaeeeeiiiiooooouuuucn'), '[^a-z0-9]+', '', 'g'), '|' order by p.n) as s
  from paginas p join documentos d on d.id = p.documento_id
  where d.texto_hash is null
  group by p.documento_id)
update documentos d set texto_hash = left(encode(sha256(convert_to(t.s, 'UTF8')), 'hex'), 40)
from t where t.documento_id = d.id and length(replace(t.s, '|', '')) >= 500;

-- 2) Figuras conferidas pela IA. Já conferidos: o que não é PDF do Drive e os PDFs sem nenhuma figura.
alter table documentos add column if not exists figuras_rev timestamptz;
update documentos set figuras_rev = now()
  where figuras_rev is null and (tipo is distinct from 'PDF' or drive_id is null);
update documentos d set figuras_rev = now()
  where d.figuras_rev is null and not exists (
    select 1 from paginas p where p.documento_id = d.id and coalesce(p.figuras, '[]'::jsonb) <> '[]'::jsonb);
create index if not exists documentos_sem_revisao on documentos (criado_em) where figuras_rev is null;

create or replace function marcar_figuras(doc uuid) returns void
language plpgsql security definer set search_path = public as $$
begin
  if not (eh_admin() or eh_robo()) then raise exception 'Só o robô marca as figuras como conferidas.'; end if;
  update documentos set figuras_rev = now() where id = doc;
end $$;
revoke all on function marcar_figuras(uuid) from public, anon;
grant execute on function marcar_figuras(uuid) to authenticated;

-- 3) Abas da biblioteca por turma. Chave da aba: letras minúsculas, números, "-" e "_" (as de sempre continuam iguais).
alter table turmas add column if not exists abas jsonb;
alter table materias drop constraint if exists materias_acervo_valido;
alter table materias add constraint materias_acervo_valido check (acervo ~ '^[a-z0-9_-]{2,40}$') not valid;
alter table materias validate constraint materias_acervo_valido;

create or replace function salvar_abas(t uuid, p_abas jsonb) returns void
language plpgsql security definer set search_path = public as $$
declare faltando text;
begin
  if t is null or not (t = any(minhas_turmas())) then raise exception 'Só quem está na turma muda as abas dela.'; end if;
  if jsonb_typeof(p_abas) <> 'array' or jsonb_array_length(p_abas) > 15 or exists (
      select 1 from jsonb_array_elements(p_abas) e
      where jsonb_typeof(e) <> 'object' or coalesce(e ->> 'k', '') !~ '^[a-z0-9_-]{2,40}$'
         or length(trim(coalesce(e ->> 'nome', ''))) not between 1 and 40) then
    raise exception 'Abas inválidas.';
  end if;
  if (select count(distinct e ->> 'k') from jsonb_array_elements(p_abas) e) <> jsonb_array_length(p_abas) then raise exception 'Abas repetidas.'; end if;
  -- aba com temas não some (as de sempre também ficam)
  select string_agg(distinct m.acervo, ', ') into faltando from materias m
    where m.turma_id = t and m.acervo not in ('faculdade', 'drive', 'residencia')
      and not exists (select 1 from jsonb_array_elements(p_abas) e where e ->> 'k' = m.acervo);
  if faltando is not null then raise exception 'Estas abas ainda têm temas e não podem ser retiradas: %', faltando; end if;
  update turmas set abas = (select jsonb_agg(jsonb_build_object('k', e ->> 'k', 'nome', trim(e ->> 'nome'))) from jsonb_array_elements(p_abas) e) where id = t;
end $$;
revoke all on function salvar_abas(uuid, jsonb) from public, anon;
grant execute on function salvar_abas(uuid, jsonb) to authenticated;

-- mandar o Drive de novo para outra aba (inclusive as criadas pela turma): mesma função do v23, aceitando as abas novas
create or replace function realocar_drive(ids text[], destino_acervo text, destino_colecao text default '')
returns json language plpgsql security definer set search_path = public as $$
declare
  col text := case when destino_acervo = 'faculdade' then coalesce(nullif(trim(destino_colecao), ''), 'Sem coleção') else '' end;
  vis uuid[] := coalesce(materias_visiveis(), '{}');
  t record; alvo uuid; inteiro boolean; k int;
  n_arq int := 0; n_mov int := 0; n_jun int := 0; n_sep int := 0; temas uuid[] := '{}';
begin
  if not eh_membro() then raise exception 'Só membros da turma podem mudar arquivos de lugar.'; end if;
  if destino_acervo !~ '^[a-z0-9_-]{2,40}$' then raise exception 'Lugar de destino inválido.'; end if;
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

-- 4) Lista de temas da turma: qualquer pessoa da turma edita (antes, só a dona)
create or replace function salvar_lista_turma(t uuid, p_texto text) returns void
language plpgsql security definer set search_path = public as $$
begin
  if t is null or not (t = any(minhas_turmas())) then raise exception 'Só quem está na turma muda a lista de temas dela.'; end if;
  if length(coalesce(p_texto, '')) > 200000 then raise exception 'Lista grande demais.'; end if;
  insert into listas (chave, texto, atualizado_em, atualizado_por) values ('temas:' || t, p_texto, now(), auth.uid())
    on conflict (chave) do update set texto = excluded.texto, atualizado_em = now(), atualizado_por = auth.uid();
end $$;
revoke all on function salvar_lista_turma(uuid, text) from public, anon;
grant execute on function salvar_lista_turma(uuid, text) to authenticated;

-- 5) Renomear especialidade (p_campo = 'periodo') ou área (p_campo = 'disciplina', dentro da especialidade p_esp), em
--    todos os temas da turma. Tema que ficaria igual a outro que já existe fica com o nome antigo (e é contado).
create or replace function renomear_lugar(t uuid, p_campo text, p_esp text, p_antigo text, p_novo text) returns json
language plpgsql security definer set search_path = public as $$
declare tt uuid := coalesce(t, turma_padrao()); novo text := regexp_replace(trim(coalesce(p_novo, '')), '\s+', ' ', 'g');
        r record; n_mud int := 0; n_fic int := 0;
begin
  if tt is null or not (tt = any(minhas_turmas())) then raise exception 'Só quem está na turma renomeia as especialidades e áreas dela.'; end if;
  if p_campo not in ('periodo', 'disciplina') then raise exception 'Pedido inválido.'; end if;
  if novo = '' or length(novo) > 80 then raise exception 'Nome inválido.'; end if;
  for r in select * from materias m where m.turma_id = tt
             and (case when p_campo = 'periodo' then m.periodo = p_antigo else m.periodo = p_esp and m.disciplina = p_antigo end) loop
    if exists (select 1 from materias x where x.turma_id = tt and x.id <> r.id and x.acervo = r.acervo and x.colecao = r.colecao and x.materia = r.materia
                 and x.periodo = case when p_campo = 'periodo' then novo else r.periodo end
                 and x.disciplina = case when p_campo = 'disciplina' then novo else r.disciplina end) then
      n_fic := n_fic + 1; continue;
    end if;
    if p_campo = 'periodo' then update materias set periodo = novo where id = r.id; else update materias set disciplina = novo where id = r.id; end if;
    n_mud := n_mud + 1;
  end loop;
  return json_build_object('mudados', n_mud, 'ficaram', n_fic);
end $$;
revoke all on function renomear_lugar(uuid, text, text, text, text) from public, anon;
grant execute on function renomear_lugar(uuid, text, text, text, text) to authenticated;

-- 6) Mudar um arquivo de tema (dentro da mesma turma). O tema de onde ele sai é refeito pela IA; se ficar sem nenhum
--    arquivo (nem áudio ou vídeo), deixa de existir.
create or replace function mover_documento(doc uuid, para uuid) returns void
language plpgsql security definer set search_path = public as $$
declare de uuid; t_de uuid; t_para uuid;
begin
  select d.materia_id, m.turma_id into de, t_de from documentos d join materias m on m.id = d.materia_id where d.id = doc;
  select m.turma_id into t_para from materias m where m.id = para;
  if de is null or t_para is null then raise exception 'Arquivo ou tema não encontrado.'; end if;
  if de = para then return; end if;
  if not (eh_admin() or (t_de = t_para and t_de = any(minhas_turmas()))) then raise exception 'Sem permissão para mudar este arquivo de tema.'; end if;
  update documentos set materia_id = para where id = doc;
  update paginas set materia_id = para where documento_id = doc;
  if not exists (select 1 from documentos where materia_id = de) and not exists (select 1 from midias where materia_id = de) then
    delete from materias where id = de;
  else
    update resumos set dados = jsonb_set(dados, '{docs}', '[]'::jsonb) where materia_id = de and dados ->> 'versao' = '4';
  end if;
end $$;
revoke all on function mover_documento(uuid, uuid) from public, anon;
grant execute on function mover_documento(uuid, uuid) to authenticated;

-- 7) Imagens do Storage que nenhuma página usa mais (com mais de 2 dias). Só o administrador e o robô (chave de serviço).
create or replace function imagens_orfas(limite int default 500) returns setof text
language plpgsql security definer set search_path = public, storage as $$
begin
  if not (eh_admin() or coalesce(auth.role(), '') = 'service_role') then raise exception 'Só o administrador.'; end if;
  return query
  with usadas as materialized (
    select substr(imagem, 4) as nome from paginas where imagem like 'sb:%'
    union select substr(f, 4) from paginas p, jsonb_array_elements_text(case when jsonb_typeof(p.figuras) = 'array' then p.figuras else '[]'::jsonb end) f where f like 'sb:%'
    union select substr(i, 4) from paginas p, unnest(p.imagens) i where i like 'sb:%'
    union select substr((regexp_matches(p.html, 'data-ref="(sb:[^"]+)"', 'g'))[1], 4) from paginas p where p.html like '%data-ref="sb:%')
  select o.name::text from storage.objects o
  where o.bucket_id = 'paginas' and o.name like 'img/%' and o.created_at < now() - interval '2 days'
    and not exists (select 1 from usadas u where u.nome = o.name)
  limit greatest(1, least(coalesce(limite, 500), 1000));
end $$;
revoke all on function imagens_orfas(int) from public, anon;
grant execute on function imagens_orfas(int) to authenticated, service_role;

analyze documentos;
select 'Pronto: ' || (select count(*) from documentos where figuras_rev is null) || ' PDFs para a IA conferir as figuras, '
  || (select count(*) from documentos where texto_hash is not null) || ' arquivos com impressão digital do texto.' as resultado;
