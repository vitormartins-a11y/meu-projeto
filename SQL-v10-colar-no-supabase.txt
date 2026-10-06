-- v10: mudar de lugar um Drive que já foi enviado, sem baixar tudo de novo
-- Quando o administrador envia de novo a mesma pasta do Drive escolhendo outro lugar (Faculdade, Drive ou Residência),
-- os arquivos que já estão no acervo vão para o lugar novo, com as páginas, as figuras e as transcrições.
--   * tema que só tinha arquivos dessa pasta: muda de lugar inteiro, com a apostila, o resumo, os flashcards e as
--     questões que a IA já fez (nada é refeito);
--   * se no lugar novo já existe um tema com o mesmo nome: os arquivos são juntados nele e a IA atualiza o tema;
--   * tema que também tinha arquivos de outros envios: só os arquivos dessa pasta saem; o tema que fica volta para a
--     fila da IA, para refazer só com o que sobrou (flashcards e questões criados pelos alunos são mantidos).
-- Pode rodar mais de uma vez sem problema.
create or replace function realocar_drive(ids text[], destino_acervo text, destino_colecao text default '')
returns json language plpgsql security definer set search_path = public as $$
declare
  col text := case when destino_acervo = 'faculdade' then coalesce(nullif(trim(destino_colecao), ''), 'Sem coleção') else '' end;
  t record; alvo uuid; inteiro boolean; k int;
  n_arq int := 0; n_mov int := 0; n_jun int := 0; n_sep int := 0; temas uuid[] := '{}';
begin
  if not eh_admin() then raise exception 'Só o administrador pode mudar arquivos de lugar.'; end if;
  if destino_acervo not in ('faculdade', 'drive', 'residencia') then raise exception 'Lugar de destino inválido.'; end if;
  if coalesce(array_length(ids, 1), 0) = 0 then
    return json_build_object('arquivos', 0, 'movidos', 0, 'juntados', 0, 'separados', 0, 'temas', '[]'::json);
  end if;
  for t in
    select m.* from materias m
    where (m.acervo <> destino_acervo or m.colecao <> col)
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
      where acervo = destino_acervo and colecao = col and periodo = t.periodo and disciplina = t.disciplina and materia = t.materia;
    if inteiro and alvo is null then          -- muda o tema inteiro de lugar, com tudo o que a IA já fez
      update materias set acervo = destino_acervo, colecao = col where id = t.id;
      n_mov := n_mov + 1; temas := temas || t.id; continue;
    end if;
    if alvo is null then
      insert into materias (periodo, disciplina, materia, acervo, colecao)
        values (t.periodo, t.disciplina, t.materia, destino_acervo, col) returning id into alvo;
    end if;
    update paginas set materia_id = alvo where documento_id in (select id from documentos where materia_id = t.id and drive_id = any(ids));
    update documentos set materia_id = alvo where materia_id = t.id and drive_id = any(ids);
    update midias set materia_id = alvo where materia_id = t.id and drive_id = any(ids);
    begin
      update falhas_envio set materia_id = alvo where materia_id = t.id and drive_id = any(ids);
    exception when undefined_table or undefined_column then null;
    end;
    if inteiro then                           -- juntou tudo no tema que já existia no destino
      update flashcards set materia_id = alvo where materia_id = t.id and origem = 'ALUNO';
      update questoes set materia_id = alvo where materia_id = t.id and origem = 'ALUNO';
      delete from materias where id = t.id;
      n_jun := n_jun + 1;
    else                                      -- o tema que fica perdeu arquivos: a IA refaz com o que sobrou
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
