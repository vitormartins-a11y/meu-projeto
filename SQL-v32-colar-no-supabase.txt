-- v32: mapa de cada arquivo (onde cada assunto começa e de que assunto da lista é cada parte). Precisa do v27.
-- Pode rodar mais de uma vez.
-- * O app (no envio) e o robô (com o que já estava no acervo) fazem o mapa uma vez só e guardam aqui. Separar, mudar de
--   lugar e reorganizar viram contas sobre o mapa: não leem o arquivo de novo e não gastam IA de novo.
-- * Uns 2 KB por arquivo.
alter table documentos add column if not exists mapa jsonb;
create index if not exists documentos_sem_mapa on documentos (criado_em) where mapa is null;

create or replace function salvar_mapa(docs uuid[], p_mapa jsonb) returns void
language plpgsql security definer set search_path = public as $$
begin
  if p_mapa is null or jsonb_typeof(p_mapa) <> 'object' or length(p_mapa::text) > 200000 then raise exception 'Mapa inválido.'; end if;
  if coalesce(array_length(docs, 1), 0) > 50 then raise exception 'Arquivos demais de uma vez.'; end if;
  if not (eh_admin() or eh_robo()) and exists (
      select 1 from documentos d join materias m on m.id = d.materia_id
      where d.id = any(docs) and not (m.turma_id = any (minhas_turmas()))) then
    raise exception 'Sem permissão para estes arquivos.';
  end if;
  update documentos set mapa = p_mapa where id = any(docs);
end $$;
revoke all on function salvar_mapa(uuid[], jsonb) from public, anon;
grant execute on function salvar_mapa(uuid[], jsonb) to authenticated;

select 'Pronto: ' || (select count(*) from documentos where mapa is null) || ' arquivos ainda sem mapa (o robô faz aos poucos).' as resultado;
