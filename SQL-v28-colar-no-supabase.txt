-- v28: "Reorganizar com IA" na biblioteca. Precisa do v27. Pode rodar mais de uma vez.
-- * Para a IA decidir o tema de cada arquivo pelo conteúdo, o app pede um resumo curto de cada arquivo:
--   os títulos das páginas (espalhados do começo ao fim do arquivo) e o começo do texto. Uns 1 KB por arquivo.
--   O texto inteiro e as imagens não saem do Supabase. O aparelho guarda o resumo e não pede de novo.
-- * Só arquivos da turma de quem pede (ou o administrador); até 300 arquivos por pedido.

create or replace function amostra_docs(docs uuid[]) returns table (id uuid, titulos text, inicio text)
language sql stable security definer set search_path = public as $$
  with alvo as (
    select d.id from documentos d join materias m on m.id = d.materia_id
    where d.id = any (docs[1:300]) and (eh_admin() or m.turma_id = any (minhas_turmas()))
  ), pags as (
    select p.documento_id, p.n,
           left(btrim(regexp_replace(coalesce(nullif(btrim(p.titulo), ''),
             split_part(btrim(regexp_replace(coalesce(p.texto, ''), '\[\[FIG:[0-9]+\]\]', '', 'g')), E'\n', 1)), '\s+', ' ', 'g')), 80) as t
    from paginas p where p.documento_id in (select a.id from alvo a)
  ), unicos as (
    -- cada título uma vez (na primeira página em que aparece)
    select documento_id, t, min(n) as n from pags where length(t) >= 3 group by documento_id, t
  ), numerados as (
    select documento_id, t, n, row_number() over (partition by documento_id order by n) as rn,
           count(*) over (partition by documento_id) as tot
    from unicos
  )
  select a.id,
    -- até uns 40 títulos, espalhados pelo arquivo inteiro
    left(coalesce((select string_agg(x.t, ' | ' order by x.n) from numerados x
      where x.documento_id = a.id and (x.tot <= 40 or (x.rn - 1) % ceil(x.tot / 40.0)::int = 0)), ''), 1200) as titulos,
    left(btrim(regexp_replace(coalesce((select string_agg(left(p.texto, 1500), ' ' order by p.n) from paginas p
      where p.documento_id = a.id and p.n in (select p2.n from paginas p2 where p2.documento_id = a.id order by p2.n limit 2)), ''),
      '\[\[FIG:[0-9]+\]\]|\s+', ' ', 'g')), 600) as inicio
  from alvo a;
$$;
revoke all on function amostra_docs(uuid[]) from public, anon;
grant execute on function amostra_docs(uuid[]) to authenticated;
