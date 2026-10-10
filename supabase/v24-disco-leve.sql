-- v24: menos uso de disco (aviso "Disk IO Budget" do Supabase grátis). Precisa do v22 e do v23. Pode rodar mais de uma vez.
-- * A "assinatura" das páginas de um tema (usada para saber se o tema mudou) passa a ser lida só do índice,
--   sem abrir as páginas no disco.
-- * Regras do cache da IA e das listas de temas: a lista de temas que a pessoa vê é calculada uma vez por consulta
--   (antes, uma vez para cada linha) e a conferência do código do tema não dá erro com chave diferente.

create index if not exists paginas_materia_atualizado on paginas (materia_id, atualizado_em);

create or replace function cache_do_meu_tema(chave text) returns boolean
language sql stable security definer set search_path = public as $$
  select case
    when eh_admin() or eh_robo() then true
    when split_part(chave, ':', 1) = 'rev' then false
    when split_part(chave, ':', 2) ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
      then split_part(chave, ':', 2)::uuid = any (coalesce(materias_visiveis(), '{}'))
    else false end;
$$;
-- leitura do cache: o "é administrador/robô?" e a lista de temas visíveis são calculados uma vez por consulta
do $$ begin
  if to_regclass('public.cache_ia') is not null then
    execute 'drop policy if exists ler on cache_ia';
    execute $p$create policy ler on cache_ia for select to authenticated using (
      (select eh_admin()) or (select eh_robo()) or (
        split_part(chave, ':', 1) <> 'rev' and case
          when split_part(chave, ':', 2) ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
            then split_part(chave, ':', 2)::uuid = any (coalesce((select materias_visiveis()), '{}'::uuid[]))
          else false end))$p$;
  end if;
  if to_regclass('public.listas') is not null then
    execute 'drop policy if exists ler on listas';
    execute $p$create policy ler on listas for select to authenticated using (
      (select eh_admin()) or chave not like 'temas:%' or case
        when split_part(chave, ':', 2) ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
          then split_part(chave, ':', 2)::uuid = any (coalesce((select minhas_turmas()), '{}'::uuid[]))
        else false end)$p$;
  end if;
end $$;

-- estatísticas atualizadas: o banco escolhe o caminho mais curto (menos leitura de disco)
analyze paginas; analyze resumos; analyze uso_ia;

select 'Pronto: o banco lê menos o disco.' as resultado;
