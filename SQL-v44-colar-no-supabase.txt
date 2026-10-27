-- v44: o robô termina o OSCE dos alunos (a pessoa não precisa ficar com a página aberta). Pode rodar mais de uma vez.
-- * robo_osce_pendentes: as estações de OSCE com temas ainda por criar (só OSCE; as anamneses continuam só do aluno).
-- * robo_salvar_osce: o robô grava as estações criadas no OSCE do aluno (só o campo das estações; o dono continua o aluno).
-- Só a conta do robô usa estas funções.

create or replace function robo_osce_pendentes() returns table (id uuid, user_id uuid, tipo text, titulo text, dados jsonb, atualizado_em timestamptz)
language plpgsql stable security definer set search_path = public as $$
begin
  if not coalesce(eh_robo(), false) then raise exception 'Só o robô.'; end if;
  return query
    select e.id, e.user_id, e.tipo, e.titulo, e.dados, e.atualizado_em from meus_estudos e
    where e.tipo = 'osce' and e.dados -> 'grupos' @> '[{"pendente": true}]'::jsonb
      and e.atualizado_em < now() - interval '2 minutes' and e.atualizado_em > now() - interval '60 days'
    order by e.atualizado_em limit 5;
end $$;
revoke all on function robo_osce_pendentes() from public, anon;
grant execute on function robo_osce_pendentes() to authenticated;

create or replace function robo_salvar_osce(p_id uuid, p_dados jsonb) returns boolean
language plpgsql security definer set search_path = public as $$
begin
  if not coalesce(eh_robo(), false) then raise exception 'Só o robô.'; end if;
  if jsonb_typeof(p_dados -> 'grupos') is distinct from 'array' then raise exception 'Estações inválidas.'; end if;
  update meus_estudos set dados = p_dados, atualizado_em = now() where id = p_id and tipo = 'osce';
  return found;
end $$;
revoke all on function robo_salvar_osce(uuid, jsonb) from public, anon;
grant execute on function robo_salvar_osce(uuid, jsonb) to authenticated;

select 'Pronto: o robô termina o OSCE dos alunos (v44).' as resultado;
