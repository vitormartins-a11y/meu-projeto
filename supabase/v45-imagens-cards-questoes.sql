-- v45: imagens em flashcards e questões. Pode rodar mais de uma vez.
-- A limpeza de imagens que nenhuma página usa (o robô apaga as com mais de 2 dias) passa a guardar também as imagens
-- dos flashcards e das questões (as figuras que a IA pôs nos cards e as imagens enviadas por quem criou o card ou a
-- questão). Sem isto, uma imagem enviada num flashcard sumiria depois de 2 dias.

create or replace function imagens_orfas(limite int default 500) returns setof text
language plpgsql security definer set search_path = public, storage as $$
begin
  if not (eh_admin() or coalesce(auth.role(), '') = 'service_role') then raise exception 'Só o administrador.'; end if;
  return query
  with usadas as materialized (
    select substr(imagem, 4) as nome from paginas where imagem like 'sb:%'
    union select substr(f, 4) from paginas p, jsonb_array_elements_text(case when jsonb_typeof(p.figuras) = 'array' then p.figuras else '[]'::jsonb end) f where f like 'sb:%'
    union select substr(i, 4) from paginas p, unnest(p.imagens) i where i like 'sb:%'
    union select substr((regexp_matches(p.html, 'data-ref="(sb:[^"]+)"', 'g'))[1], 4) from paginas p where p.html like '%data-ref="sb:%'
    union select substr((regexp_matches(f.extras::text, '"(sb:img/[^"]+)"', 'g'))[1], 4) from flashcards f where f.extras::text like '%sb:img/%'
    union select substr((regexp_matches(q.extras::text, '"(sb:img/[^"]+)"', 'g'))[1], 4) from questoes q where q.extras::text like '%sb:img/%')
  select o.name::text from storage.objects o
  where o.bucket_id = 'paginas' and o.name like 'img/%' and o.created_at < now() - interval '2 days'
    and not exists (select 1 from usadas u where u.nome = o.name)
  limit greatest(1, least(coalesce(limite, 500), 1000));
end $$;
revoke all on function imagens_orfas(int) from public, anon;
grant execute on function imagens_orfas(int) to authenticated, service_role;

select 'Pronto: as imagens dos flashcards e das questões ficam guardadas (v45).' as resultado;
