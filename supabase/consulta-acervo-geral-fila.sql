-- Por que o acervo geral não anda na fila da IA? Só lê; não muda nada. Rode no Supabase (SQL Editor) e mande o resultado das 3.

-- 1) o foco da fila (se tiver "escopos", a IA só trabalha nesses grupos)
select dados from cache_ia where chave = 'ia:foco';

-- 2) os temas do acervo geral: quantos arquivos, quantos ficaram só para consulta e se já têm apostila
select m.periodo as especialidade, m.disciplina as area, m.materia as tema, m.acervo,
  (select count(*) from documentos d where d.materia_id = m.id) as arquivos,
  (select count(*) from documentos d where d.materia_id = m.id and d.uso_ia = 'consulta') as so_consulta,
  coalesce(r.dados->>'versao', '—') as versao,
  length(coalesce(r.dados->>'apostila', '')) > 0 as tem_apostila
from materias m
join turmas t on t.id = m.turma_id and t.geral
left join resumos r on r.materia_id = m.id
order by m.periodo, m.materia;

-- 3) o robô: o último pedido de IA que ele fez (horário de Brasília)
select to_char(max(em) at time zone 'America/Sao_Paulo', 'DD/MM HH24:MI') as ultimo_pedido_do_robo from uso_ia where origem = 'robo';
