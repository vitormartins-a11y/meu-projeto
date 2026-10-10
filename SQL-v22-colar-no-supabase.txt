-- v22: menos tráfego (Egress) no Supabase grátis
-- O site passa a guardar no aparelho de cada aluno as páginas dos temas e só baixa de novo quando alguma muda.
-- Para saber se mudou sem baixar tudo, cada página ganha a data da última mudança, e o site pergunta só uma
-- "assinatura" curta do tema (quantas páginas + a mudança mais recente).
-- Pode rodar mais de uma vez sem problema.

alter table paginas add column if not exists atualizado_em timestamptz not null default now();
create or replace function paginas_tocar() returns trigger language plpgsql as $$
begin new.atualizado_em := now(); return new; end $$;
drop trigger if exists paginas_tocar on paginas;
create trigger paginas_tocar before update on paginas for each row execute function paginas_tocar();

-- o resumo do tema também marca a hora pelo relógio do servidor (o site compara essa hora antes de baixar o tema)
create or replace function resumos_tocar() returns trigger language plpgsql as $$
begin
  if tg_op = 'INSERT' or new.dados is distinct from old.dados then new.atualizado_em := now(); end if;
  return new;
end $$;
drop trigger if exists resumos_tocar on resumos;
create trigger resumos_tocar before insert or update on resumos for each row execute function resumos_tocar();

create or replace function assinatura_paginas(m uuid) returns text
language sql stable set search_path = public as $$
  select count(*)::text || '-' || coalesce(extract(epoch from max(atualizado_em))::text, '') from paginas where materia_id = m;
$$;
revoke all on function assinatura_paginas(uuid) from public, anon;
grant execute on function assinatura_paginas(uuid) to authenticated;

select 'Pronto: o site agora baixa bem menos coisa do Supabase.' as resultado;
