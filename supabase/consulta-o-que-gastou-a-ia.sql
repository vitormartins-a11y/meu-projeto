-- O que gastou a IA desde que a cota do dia recomeçou (meia-noite no Pacífico = 5h em Brasília).
-- Só lê; não muda nada. Rode no Supabase (SQL Editor) e mande o resultado das duas consultas.
-- Mostra só o final de cada chave (os 4 últimos caracteres), nunca a chave nem o e-mail.

-- 1) por chave, modelo e tarefa: quantos pedidos foram atendidos (cada atendido gasta 1 da cota daquele modelo naquela chave)
select
  coalesce('…' || k.final, case when u.chave_id is null then 'chave do site' else 'chave ' || left(u.chave_id, 6) end) as chave,
  u.provedor,
  coalesce(u.modelo, '—') as modelo,
  coalesce(u.tarefa, '—') as tarefa,
  coalesce(u.origem, '—') as origem,
  coalesce(m.materia, '(sem tema)') as tema,
  count(*) filter (where u.ok) as atendidos,
  count(*) filter (where not u.ok) as recusados,
  to_char(min(u.em) at time zone 'America/Sao_Paulo', 'DD/MM HH24:MI') as primeiro,
  to_char(max(u.em) at time zone 'America/Sao_Paulo', 'DD/MM HH24:MI') as ultimo
from uso_ia u
left join chaves_api k on k.chave_id = u.chave_id
left join materias m on m.id = u.materia_id
where u.em >= (date_trunc('day', now() at time zone 'America/Los_Angeles') at time zone 'America/Los_Angeles')
group by 1, 2, 3, 4, 5, 6
order by atendidos desc, recusados desc
limit 150;

-- 2) hora a hora nas últimas 24 horas: quando a IA trabalhou e em quê
select
  to_char(date_trunc('hour', u.em) at time zone 'America/Sao_Paulo', 'DD/MM HH24":00"') as hora,
  coalesce(u.tarefa, '—') as tarefa,
  coalesce(u.origem, '—') as origem,
  u.provedor,
  count(*) filter (where u.ok) as atendidos,
  count(*) filter (where not u.ok) as recusados
from uso_ia u
where u.em >= now() - interval '24 hours'
group by 1, 2, 3, 4
order by 1, atendidos desc;
