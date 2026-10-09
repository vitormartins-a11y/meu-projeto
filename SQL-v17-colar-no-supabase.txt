-- v17: as chaves guardadas dos alunos passam a ajudar também nas ferramentas de estudo (Anamneses, OSCE, Material de estudo)
-- Regra: 10% das chaves (no mínimo 1) ficam de reserva para as ferramentas de estudo; o robô nunca usa a reserva.
-- Quando o robô não está trabalhando, todas as chaves ficam livres para as ferramentas de estudo (o robô não está gastando).
-- Quem está usando o site tem prioridade: usa primeiro a reserva e, se ela acabar, qualquer chave livre.
-- Pode rodar mais de uma vez sem problema.

-- quais chaves são a reserva (sempre as mesmas, para o robô não gastar a cota do dia delas)
create or replace function chaves_reserva() returns uuid[]
language sql stable security definer set search_path = public as $$
  with boas as (select user_id from chaves_ia where ativa and recusada_em is null)
  select coalesce(array_agg(user_id), '{}') from (
    select user_id from boas order by user_id
    limit (select greatest(1, ceil(count(*) * 0.10))::int from boas)) r;
$$;
revoke all on function chaves_reserva() from public, anon, authenticated;
grant execute on function chaves_reserva() to service_role;

-- a função "ia" pega a chave: modo 'fila' (robô) fora da reserva; modo 'estudo' (alunos) a reserva primeiro, depois qualquer uma
create or replace function pegar_chave_turma(evitar uuid[] default '{}', modo text default 'fila')
returns table (user_id uuid, cifrada text, chave_id text, reserva boolean)
language plpgsql security definer set search_path = public as $$
declare res uuid[] := chaves_reserva();
begin
  return query
  update chaves_ia c set ultimo_uso = now()
  where c.user_id = (select k.user_id from chaves_ia k
                     where k.ativa and k.recusada_em is null and coalesce(k.descanso_ate, '-infinity') < now() and not (k.user_id = any(evitar))
                       and (modo = 'estudo' or not (k.user_id = any(res)))
                     order by case when modo = 'estudo' and k.user_id = any(res) then 0 else 1 end, k.ultimo_uso nulls first
                     limit 1 for update skip locked)
  returning c.user_id, c.cifrada, c.chave_id, c.user_id = any(res);
end $$;
revoke all on function pegar_chave_turma(uuid[], text) from public, anon, authenticated;
grant execute on function pegar_chave_turma(uuid[], text) to service_role;

-- quantas chaves o robô pode usar agora (sem contar a reserva): ele decide por aqui quantas partes faz de uma vez
create or replace function chaves_guardadas_disponiveis() returns int
language sql stable security definer set search_path = public as $$
  select case when eh_membro() then (select count(*)::int from chaves_ia
    where ativa and recusada_em is null and coalesce(descanso_ate, '-infinity') < now() and not (user_id = any(chaves_reserva()))) else 0 end;
$$;
revoke all on function chaves_guardadas_disponiveis() from public, anon;
grant execute on function chaves_guardadas_disponiveis() to authenticated;
