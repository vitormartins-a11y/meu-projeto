-- v53: a lista "Arquivos grandes" da Administração conta as páginas só dos arquivos da turma aberta, um arquivo por vez
-- pelo índice (antes, contava as páginas de todos os arquivos de todas as turmas juntas e passava do tempo do banco:
-- "canceling statement due to statement timeout"). Só lê; não muda nada. Pode rodar mais de uma vez.
create index if not exists paginas_documento on paginas (documento_id);
create or replace function docs_grandes_turma(t uuid, min_paginas int default 150)
returns table (id uuid, materia_id uuid, nome text, tipo text, paginas bigint, uso_ia text)
language plpgsql stable security definer set search_path = public as $$
begin
  if not (eh_admin() or coalesce(auth.role(), '') = 'service_role') then raise exception 'Só o administrador.'; end if;
  return query
    select d.id, d.materia_id, d.nome, d.tipo, c.n as paginas, d.uso_ia
      from documentos d
      join materias m on m.id = d.materia_id and m.turma_id = t
      cross join lateral (select count(*) as n from paginas p where p.documento_id = d.id) c
     where c.n > min_paginas or d.uso_ia is not null
     order by c.n desc
     limit 1000;
end $$;
revoke all on function docs_grandes_turma(uuid, int) from public, anon;
grant execute on function docs_grandes_turma(uuid, int) to authenticated;
select 'v53 ok' as resultado;
