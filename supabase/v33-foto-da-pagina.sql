-- v33: "Ver página inteira" em cada figura da apostila. Precisa do v32. Pode rodar mais de uma vez.
-- * A foto da página inteira só fica guardada quando o recorte da figura parece errado (o resto ocuparia espaço demais).
--   Nas outras páginas, quem toca em "Ver página inteira" deixa um pedido aqui; o robô do computador baixa o PDF do Drive,
--   tira a foto daquela página e guarda (para a turma toda). O aparelho do aluno nunca lê o Drive.
-- * "Corte errado: usar a página inteira" (quem organiza): a figura passa a ser a página inteira, sem gastar IA.
create table if not exists fotos_pedidas (
  pagina_id uuid primary key references paginas(id) on delete cascade,
  documento_id uuid not null references documentos(id) on delete cascade,
  trocar int,                                   -- número da figura a trocar pela página inteira (corte errado), ou nada
  user_id uuid default auth.uid(),
  pedido_em timestamptz not null default now()
);
alter table fotos_pedidas enable row level security;
drop policy if exists ler on fotos_pedidas;
create policy ler on fotos_pedidas for select to authenticated using ((select eh_membro()) or (select eh_robo()) or (select eh_admin()));
drop policy if exists pedir on fotos_pedidas;
create policy pedir on fotos_pedidas for insert to authenticated with check (
  user_id = (select auth.uid()) and exists (
    select 1 from paginas p join materias m on m.id = p.materia_id
    where p.id = pagina_id and p.documento_id = fotos_pedidas.documento_id
      and ((select eh_admin()) or m.turma_id = any (coalesce((select minhas_turmas()), '{}'::uuid[])))));
drop policy if exists apagar on fotos_pedidas;
create policy apagar on fotos_pedidas for delete to authenticated using ((select eh_robo()) or (select eh_admin()));
create index if not exists fotos_pedidas_em on fotos_pedidas (pedido_em);

-- o robô guarda a foto da página (e, se o pedido era "corte errado", troca a figura pela página inteira)
create or replace function guardar_foto_pagina(pid uuid, ref text) returns void
language plpgsql security definer set search_path = public as $$
declare t int;
begin
  if not (eh_robo() or eh_admin()) then raise exception 'Só o robô guarda a foto da página.'; end if;
  if ref is null or length(ref) > 300 then raise exception 'Foto inválida.'; end if;
  select trocar into t from fotos_pedidas where pagina_id = pid;
  update paginas set imagem = coalesce(imagem, ref) where id = pid;
  if t is not null then
    update paginas set figuras = jsonb_set(coalesce(figuras, '[]'::jsonb), array[t::text], to_jsonb(coalesce(imagem, ref)), true)
      where id = pid and t >= 0 and t < 200;
  end if;
  delete from fotos_pedidas where pagina_id = pid;
end $$;
revoke all on function guardar_foto_pagina(uuid, text) from public, anon;
grant execute on function guardar_foto_pagina(uuid, text) to authenticated;

-- pedido que não dá para atender (arquivo sem Drive, página que não abre): sai da fila
create or replace function desistir_foto_pagina(pid uuid) returns void
language plpgsql security definer set search_path = public as $$
begin
  if not (eh_robo() or eh_admin()) then raise exception 'Só o robô.'; end if;
  delete from fotos_pedidas where pagina_id = pid;
end $$;
revoke all on function desistir_foto_pagina(uuid) from public, anon;
grant execute on function desistir_foto_pagina(uuid) to authenticated;

-- "corte errado" com a foto já guardada: a figura vira a página inteira na hora (quem organiza a turma)
create or replace function figura_pela_pagina(pid uuid, n int) returns void
language plpgsql security definer set search_path = public as $$
begin
  if n is null or n < 0 or n >= 200 then raise exception 'Figura inválida.'; end if;
  if not exists (select 1 from paginas p join materias m on m.id = p.materia_id where p.id = pid
                 and (eh_admin() or eh_robo() or m.turma_id = any (coalesce(minhas_turmas(), '{}'::uuid[])))) then
    raise exception 'Sem permissão.';
  end if;
  update paginas set figuras = jsonb_set(coalesce(figuras, '[]'::jsonb), array[n::text], to_jsonb(imagem), true)
    where id = pid and imagem is not null;
end $$;
revoke all on function figura_pela_pagina(uuid, int) from public, anon;
grant execute on function figura_pela_pagina(uuid, int) to authenticated;

select 'Pronto: "Ver página inteira" ligado (' || (select count(*) from fotos_pedidas) || ' pedidos na fila).' as resultado;
