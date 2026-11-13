-- v54: apagar as páginas de um arquivo aos poucos (só o administrador). Usado por "Apagar o material do acervo geral":
-- um arquivo grande tem milhares de páginas e, de uma vez só, passava do tempo do banco. Pode rodar mais de uma vez.
create or replace function apagar_paginas_lote(p_doc uuid, p_lim int default 1000) returns int
language plpgsql security definer set search_path = public as $$
declare n int;
begin
  if not eh_admin() then raise exception 'Só o administrador.'; end if;
  delete from paginas where id in (select id from paginas where documento_id = p_doc limit greatest(1, least(coalesce(p_lim, 1000), 5000)));
  get diagnostics n = row_count;
  return n;
end $$;
revoke all on function apagar_paginas_lote(uuid, int) from public, anon;
grant execute on function apagar_paginas_lote(uuid, int) to authenticated;
select 'v54 ok' as resultado;
