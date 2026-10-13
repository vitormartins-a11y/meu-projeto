-- v29: site econômico para a turma inteira. Pode rodar antes ou depois do v28. Pode rodar mais de uma vez.
-- * "Assinatura" de cada tema (quantos flashcards ou questões ele tem e quando chegou o último): o aparelho guarda
--   os cards e as questões e só baixa de novo os temas cuja assinatura mudou. Antes, um card novo em qualquer tema
--   fazia o aparelho baixar todos os flashcards de novo.
--   A assinatura também leva o tamanho total das linhas: um card ou questão corrigido sem mudar a quantidade também conta.
-- * Só os temas das turmas de quem pede (ou o administrador); t = uma turma só.

drop function if exists assinatura_itens(text, uuid);
create or replace function assinatura_itens(tabela text, t uuid default null)
returns table (materia_id uuid, n bigint, ult timestamptz, tam bigint)
language plpgsql stable security definer set search_path = public as $$
begin
  if tabela not in ('flashcards', 'questoes') then raise exception 'Tabela inválida.'; end if;
  return query execute format(
    'select x.materia_id, count(*), max(x.criado_em), sum(pg_column_size(x.*))::bigint from %I x join materias m on m.id = x.materia_id
     where ($1 is null or m.turma_id = $1) and (eh_admin() or m.turma_id = any (minhas_turmas()))
     group by x.materia_id', tabela) using t;
end $$;
revoke all on function assinatura_itens(text, uuid) from public, anon;
grant execute on function assinatura_itens(text, uuid) to authenticated;

-- o progresso de cada pessoa é lido aos poucos (só o que mudou desde a última vez)
create index if not exists progresso_usuario_atualizado on progresso (user_id, atualizado_em);
create index if not exists eventos_usuario_em on eventos (user_id, em);
