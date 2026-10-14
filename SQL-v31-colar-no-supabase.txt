-- v31: mudar um arquivo de tema leva junto o registro do vídeo ou áudio de onde ele veio (a transcrição).
-- Assim o tema "A organizar" (ou o antigo) não fica com o vídeo para trás e some quando ficar vazio. Precisa do v27.
-- Pode rodar mais de uma vez.
create or replace function mover_documento(doc uuid, para uuid) returns void
language plpgsql security definer set search_path = public as $$
declare de uuid; t_de uuid; t_para uuid;
begin
  select d.materia_id, m.turma_id into de, t_de from documentos d join materias m on m.id = d.materia_id where d.id = doc;
  select m.turma_id into t_para from materias m where m.id = para;
  if de is null or t_para is null then raise exception 'Arquivo ou tema não encontrado.'; end if;
  if de = para then return; end if;
  if not (eh_admin() or (t_de = t_para and t_de = any(minhas_turmas()))) then raise exception 'Sem permissão para mudar este arquivo de tema.'; end if;
  update documentos set materia_id = para, conferir = false where id = doc;
  update paginas set materia_id = para where documento_id = doc;
  update midias set materia_id = para where documento_id = doc and materia_id = de;
  if not exists (select 1 from documentos where materia_id = de) and not exists (select 1 from midias where materia_id = de) then
    delete from materias where id = de;
  else
    update resumos set dados = jsonb_set(dados, '{docs}', '[]'::jsonb) where materia_id = de and dados ->> 'versao' = '4';
  end if;
end $$;
revoke all on function mover_documento(uuid, uuid) from public, anon;
grant execute on function mover_documento(uuid, uuid) to authenticated;
