-- v36: a chave de reserva (guardada para as ferramentas de estudo dos alunos) também ajuda a fila da IA quando todas as
-- outras chaves estão sem cota. Antes ela ficava parada o dia inteiro se ninguém usasse Anamneses, OSCE ou Material.
-- As ferramentas de estudo continuam usando só a reserva (e, sem cota nela, o Groq). Pode rodar mais de uma vez.
create or replace function pegar_chave_turma(evitar uuid[] default '{}', modo text default 'fila')
returns table (user_id uuid, cifrada text, chave_id text, reserva boolean)
language plpgsql security definer set search_path = public as $$
declare res uuid[] := chaves_reserva();
begin
  return query
  update chaves_ia c set ultimo_uso = now()
  where c.user_id = (select k.user_id from chaves_ia k
                     where k.ativa and k.recusada_em is null and coalesce(k.descanso_ate, '-infinity') < now() and not (k.user_id = any(evitar))
                       and (modo = 'fila' or k.user_id = any(res))
                     -- a fila usa primeiro as chaves de fora da reserva; a reserva só quando não sobra nenhuma
                     order by (k.user_id = any(res)), k.ultimo_uso nulls first
                     limit 1 for update skip locked)
  returning c.user_id, c.cifrada, c.chave_id, c.user_id = any(res);
end $$;
revoke all on function pegar_chave_turma(uuid[], text) from public, anon, authenticated;
grant execute on function pegar_chave_turma(uuid[], text) to service_role;
