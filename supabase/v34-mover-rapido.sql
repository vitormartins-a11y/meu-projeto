-- v34: mudar arquivo de tema sem estourar o tempo ("canceling statement due to statement timeout"). Pode rodar mais de uma vez.
-- * Faltava um índice das páginas pelo arquivo: para mudar UM arquivo de tema, o banco lia TODAS as páginas do acervo e
--   passava do limite de 8 segundos do Supabase. Com o índice, cada mudança leva milésimos de segundo.
-- * O mesmo para apagar um arquivo (as páginas dele saem junto) e para áudios/vídeos e fotos pedidas de um arquivo.
-- * mover_documento não regrava as páginas que já estão no tema certo (útil quando uma mudança parou no meio).
-- Criar o índice pode levar 1 ou 2 minutos num acervo grande. Rode tudo de uma vez.
create index if not exists paginas_documento on paginas (documento_id);
do $$ begin
  if exists (select 1 from information_schema.columns where table_schema = 'public' and table_name = 'midias' and column_name = 'documento_id') then
    execute 'create index if not exists midias_documento on midias (documento_id)';
  end if;
  if exists (select 1 from information_schema.tables where table_schema = 'public' and table_name = 'fotos_pedidas') then
    execute 'create index if not exists fotos_pedidas_documento on fotos_pedidas (documento_id)';
  end if;
end $$;

create or replace function mover_documento(doc uuid, para uuid) returns void
language plpgsql security definer set search_path = public as $$
declare de uuid; t_de uuid; t_para uuid;
begin
  select d.materia_id, m.turma_id into de, t_de from documentos d join materias m on m.id = d.materia_id where d.id = doc;
  select m.turma_id into t_para from materias m where m.id = para;
  if de is null or t_para is null then raise exception 'Arquivo ou tema não encontrado.'; end if;
  if not (eh_admin() or (t_de = t_para and t_de = any(minhas_turmas()))) then raise exception 'Sem permissão para mudar este arquivo de tema.'; end if;
  -- (páginas que ficaram para trás numa mudança que parou no meio também vêm)
  update paginas set materia_id = para where documento_id = doc and materia_id is distinct from para;
  if de = para then return; end if;
  update documentos set materia_id = para, conferir = false where id = doc;
  update midias set materia_id = para where documento_id = doc and materia_id = de;
  if not exists (select 1 from documentos where materia_id = de) and not exists (select 1 from midias where materia_id = de) then
    delete from materias where id = de;
  else
    update resumos set dados = jsonb_set(dados, '{docs}', '[]'::jsonb) where materia_id = de and dados ->> 'versao' = '4';
  end if;
end $$;
revoke all on function mover_documento(uuid, uuid) from public, anon;
grant execute on function mover_documento(uuid, uuid) to authenticated;
analyze paginas;
