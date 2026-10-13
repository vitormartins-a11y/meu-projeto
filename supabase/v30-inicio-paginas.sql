-- v30: para separar um "caderno completo" pelos assuntos da lista. Pode rodar mais de uma vez.
-- * O Reorganizar com IA lê, de cada página do caderno, só o título e o começo do texto (160 letras), sem baixar o
--   texto inteiro: é onde aparece o nome do capítulo ("Acalásia", "Doença de Crohn e RCU"...).
-- * Só arquivos da turma de quem pede (ou o administrador); até 500 páginas por pedido.

create or replace function inicio_paginas(doc uuid, de int default 0, qtd int default 500)
returns table (id uuid, documento_id uuid, n int, titulo text, texto text)
language sql stable security definer set search_path = public as $$
  select p.id, p.documento_id, p.n, p.titulo,
         left(btrim(regexp_replace(coalesce(p.texto, ''), '\[\[FIG:[0-9]+\]\]', '', 'g')), 160)
  from paginas p join documentos d on d.id = p.documento_id join materias m on m.id = d.materia_id
  where p.documento_id = doc and (eh_admin() or m.turma_id = any (minhas_turmas()))
  order by p.n offset greatest(de, 0) limit least(greatest(qtd, 1), 500);
$$;
revoke all on function inicio_paginas(uuid, int, int) from public, anon;
grant execute on function inicio_paginas(uuid, int, int) to authenticated;
