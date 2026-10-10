-- TESTE DE SEGURANÇA ("teste como um estranho"). Não muda nada no banco: só lê, fingindo ser
--   (1) alguém sem conta (anon) e (2) alguém com conta mas fora de todas as turmas (estranho).
-- Cole no SQL Editor do Supabase e clique em Run. Pode rodar quantas vezes quiser.
-- No resultado, a coluna "resultado" deve dizer OK em todas as linhas. Se aparecer PROBLEMA, me mande o print.
begin;
create temp table resultado_teste (quem text, onde text, linhas text, resultado text) on commit drop;
grant all on resultado_teste to anon, authenticated;

do $$
declare
  t text; n bigint; quem text; claims text;
  publicas text[] := array['cursos', 'turmas'];          -- só nomes de cursos aprovados e de turmas (sem código)
  estranho uuid := gen_random_uuid();
begin
  foreach quem in array array['sem conta (anon)', 'estranho com conta'] loop
    claims := case when quem like 'sem%' then '{"role":"anon"}'
      else json_build_object('sub', estranho, 'email', 'estranho-teste@exemplo.invalid', 'role', 'authenticated')::text end;
    for t in select c.relname from pg_class c join pg_namespace s on s.oid = c.relnamespace
             where s.nspname = 'public' and c.relkind in ('r', 'v', 'm') order by 1 loop
      perform set_config('request.jwt.claims', claims, true);
      perform set_config('request.jwt.claim.sub', case when quem like 'sem%' then '' else estranho::text end, true);
      execute case when quem like 'sem%' then 'set local role anon' else 'set local role authenticated' end;
      begin
        execute format('select count(*) from public.%I', t) into n;
      exception when insufficient_privilege then n := -1;
      end;
      reset role;
      insert into resultado_teste values (quem, 'tabela ' || t, case when n < 0 then 'bloqueada' else n::text end,
        case when n <= 0 then 'OK' when t = any (publicas) and quem not like 'sem%' then 'OK (só nomes, é de propósito)' else 'PROBLEMA: vê dados' end);
    end loop;
    -- arquivos guardados (imagens das apostilas, fotos pessoais)
    perform set_config('request.jwt.claims', claims, true);
    perform set_config('request.jwt.claim.sub', case when quem like 'sem%' then '' else estranho::text end, true);
    execute case when quem like 'sem%' then 'set local role anon' else 'set local role authenticated' end;
    begin
      select count(*) into n from storage.objects where bucket_id in ('paginas', 'pessoal');
    exception when insufficient_privilege then n := -1;
    end;
    reset role;
    insert into resultado_teste values (quem, 'arquivos das apostilas e fotos pessoais', case when n < 0 then 'bloqueada' else n::text end,
      case when n <= 0 then 'OK' else 'PROBLEMA: vê arquivos' end);
  end loop;
end $$;

-- funções que só o administrador ou a dona podem usar: o estranho tem que ser barrado
do $$
declare f text; ok boolean; msg text; n bigint;
begin
  perform set_config('request.jwt.claims', json_build_object('sub', gen_random_uuid(), 'email', 'estranho-teste@exemplo.invalid', 'role', 'authenticated')::text, true);
  foreach f in array array['select admin_resumo()', 'select codigo_da_turma(turma_padrao())', 'select * from admin_turmas()',
                            'select * from admin_tokens(now() - interval ''1 day'')', 'select admin_usuario(gen_random_uuid())', 'select trocar_codigo(turma_padrao(), ''HACKER1'')'] loop
    set local role authenticated;
    msg := null;
    begin
      execute format('select count(*) from (%s) x where jsonb_strip_nulls(to_jsonb(x)) <> ''{}''::jsonb', f) into n;
      ok := n = 0; msg := case when n = 0 then 'não devolveu nada' end;
    exception when undefined_function then ok := true; msg := 'não existe neste banco';
              when others then ok := true;
    end;
    reset role;
    insert into resultado_teste values ('estranho com conta', 'função: ' || split_part(f, '(', 1), coalesce(msg, case when ok then 'barrada' else 'executou' end),
      case when ok then 'OK' else 'PROBLEMA: estranho usou função restrita' end);
  end loop;
end $$;

select quem, onde, linhas, resultado from resultado_teste order by (resultado like 'PROBLEMA%') desc, quem, onde;
rollback;   -- nada fica gravado
