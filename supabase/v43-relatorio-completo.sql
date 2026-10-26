-- v43: relatório completo de uso para pesquisa (só o administrador vê). Pode rodar mais de uma vez. Precisa do v41 e do v42.
-- * eventos.resposta e eventos.extra: a letra marcada em cada questão (com o gabarito daquela hora), a resposta de cada
--   flashcard, até onde a pessoa leu cada apostila ou resumo, e as anamneses, materiais e OSCE montados (das anamneses,
--   só a quantidade: o conteúdo nunca entra no relatório).
-- * osce_registros: cada simulação ou treino de OSCE inteiro (a conversa, o checklist item por item e a nota).
-- * consentimentos: quem autorizou o uso anônimo dos dados em pesquisa.
-- * relatorio_excluidos: contas que o administrador tira dos relatórios (contas pessoais, de teste).
-- * Funções novas: admin_aluno_dia (tudo de um dia de um aluno), admin_osce (um atendimento inteiro), admin_geral
--   (relatório geral com os nomes), admin_turma_dia (quem estudou num dia e o quê), admin_excluir (tirar ou devolver uma
--   conta). Refeitas: admin_aluno (com OSCE, anamneses, leitura e autorização), admin_impacto e admin_alunos (sem as contas
--   tiradas) e admin_resumo (a coluna "Na turma" passa a contar quem entrou pela turma).

alter table eventos add column if not exists resposta text;
alter table eventos add column if not exists extra jsonb;
create index if not exists eventos_usuario_em on eventos (user_id, em);
create index if not exists eventos_item on eventos (user_id, tipo, item_id, em);

create table if not exists osce_registros (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references auth.users on delete cascade,
  tipo text not null check (tipo in ('simulacao', 'treino')),
  estudo_id uuid, grupo int, caso int, materia_id uuid,
  estacao text check (length(estacao) <= 300), porta text check (length(porta) <= 6000), diagnostico text check (length(diagnostico) <= 1000),
  nota numeric, itens_total int, itens_feitos int, duracao_seg int,
  geral text check (length(geral) <= 4000), corrigido_pela_ia boolean,
  checklist jsonb check (octet_length(checklist::text) <= 200000),
  conversa jsonb check (octet_length(conversa::text) <= 600000),
  em timestamptz not null default now());
create index if not exists osce_registros_usuario on osce_registros (user_id, em);
alter table osce_registros enable row level security;
drop policy if exists registrar on osce_registros;
create policy registrar on osce_registros for insert to authenticated with check (user_id = (select auth.uid()));
drop policy if exists ler on osce_registros;
create policy ler on osce_registros for select to authenticated using (user_id = (select auth.uid()) or (select eh_admin()));
drop policy if exists apagar on osce_registros;
create policy apagar on osce_registros for delete to authenticated using (user_id = (select auth.uid()));

create table if not exists consentimentos (
  user_id uuid primary key default auth.uid() references auth.users on delete cascade,
  aceitou boolean not null, versao int not null default 1, em timestamptz not null default now());
alter table consentimentos enable row level security;
drop policy if exists meu on consentimentos;
create policy meu on consentimentos for select to authenticated using (user_id = (select auth.uid()) or (select eh_admin()));
drop policy if exists responder on consentimentos;
create policy responder on consentimentos for insert to authenticated with check (user_id = (select auth.uid()));
drop policy if exists mudar on consentimentos;
create policy mudar on consentimentos for update to authenticated using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

create table if not exists relatorio_excluidos (
  user_id uuid primary key references auth.users on delete cascade,
  em timestamptz not null default now());
alter table relatorio_excluidos enable row level security;   -- sem políticas: só pelas funções do administrador

-- entra nos relatórios: não é administrador e não foi tirada pelo administrador
create or replace function rel_conta_ok(u uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select not exists (select 1 from relatorio_excluidos x where x.user_id = u)
     and not exists (select 1 from auth.users w join admins a on lower(a.email) = lower(w.email) where w.id = u);
$$;
revoke all on function rel_conta_ok(uuid) from public, anon, authenticated;

create or replace function admin_excluir(p_user uuid, p_fora boolean) returns boolean
language plpgsql security definer set search_path = public as $$
begin
  if not eh_admin() then raise exception 'Só o administrador.'; end if;
  if p_fora then insert into relatorio_excluidos (user_id) values (p_user) on conflict (user_id) do nothing;
  else delete from relatorio_excluidos where user_id = p_user; end if;
  return p_fora;
end $$;
revoke all on function admin_excluir(uuid, boolean) from public, anon;
grant execute on function admin_excluir(uuid, boolean) to authenticated;

-- um atendimento de OSCE inteiro
create or replace function admin_osce(p_id uuid) returns json
language plpgsql stable security definer set search_path = public as $$
declare r json;
begin
  if not eh_admin() then raise exception 'Só o administrador.'; end if;
  select json_build_object('registro', to_json(o), 'materia', m.materia, 'periodo', m.periodo, 'email', u.email::text,
         'nome', coalesce(u.raw_user_meta_data ->> 'nome', u.raw_user_meta_data ->> 'full_name'))
    into r from osce_registros o left join materias m on m.id = o.materia_id left join auth.users u on u.id = o.user_id where o.id = p_id;
  return r;
end $$;
revoke all on function admin_osce(uuid) from public, anon;
grant execute on function admin_osce(uuid) to authenticated;

-- tudo o que um aluno fez num dia (dia no horário de Brasília)
create or replace function admin_aluno_dia(p_user uuid, p_dia date) returns json
language plpgsql stable security definer set search_path = public as $$
declare ini timestamptz := p_dia::timestamp at time zone 'America/Sao_Paulo';
        fim timestamptz := (p_dia + 1)::timestamp at time zone 'America/Sao_Paulo'; r json;
begin
  if not eh_admin() then raise exception 'Só o administrador.'; end if;
  with
  ac as (select a.* from acessos a where a.user_id = p_user and a.inicio >= ini and a.inicio < fim and a.segundos > 0),
  ev as (select e.* from eventos e where e.user_id = p_user and e.em >= ini and e.em < fim),
  an as (select id from meus_estudos where user_id = p_user and tipo = 'caso' and criado_em >= ini and criado_em < fim
         union select item_id from ev where tipo = 'anamnese' and item_id is not null),
  oc as (select id from meus_estudos where user_id = p_user and tipo = 'osce' and criado_em >= ini and criado_em < fim
         union select item_id from ev where tipo = 'osce_criado' and item_id is not null),
  mids as (select materia_id from ac where materia_id is not null union select materia_id from ev where materia_id is not null)
  select json_build_object(
    'dia', p_dia,
    'resumo', json_build_object(
      'segundos', (select coalesce(sum(segundos), 0) from ac), 'telas', (select count(*) from ac),
      'primeiro', (select min(inicio) from ac), 'ultimo', (select max(inicio + make_interval(secs => segundos)) from ac),
      'questoes', (select count(*) from ev where tipo = 'q'), 'certas', (select count(*) from ev where tipo = 'q' and acertou),
      'erradas', (select count(*) from ev where tipo = 'q' and acertou = false), 'sem_gabarito', (select count(*) from ev where tipo = 'q' and acertou is null),
      'flashcards', (select count(*) from ev where tipo = 'fc'),
      'osce', (select count(*) from ev where tipo in ('osce_sim', 'osce_prova')),
      'anamneses', (select count(*) from an), 'osce_criados', (select count(*) from oc),
      'materiais_criados', (select count(*) from ev where tipo = 'material'),
      'lidos', (select count(distinct materia_id) from ev where tipo = 'leitura'),
      'abertos', (select count(distinct materia_id) from ac where aba in ('conteudo', 'resumo', 'original')),
      'estudou_apos_erro', (select count(*) from ev where tipo = 'estudo_q'),
      'ia', (select count(*) from uso_ia u where u.pediu = p_user and u.em >= ini and u.em < fim and u.ok)),
    'telas', (select coalesce(json_agg(x order by x.inicio), '[]') from (
        select ac.inicio, ac.segundos, ac.aba, ac.rota, ac.aparelho, ac.materia_id, m.materia, m.periodo
        from ac left join materias m on m.id = ac.materia_id) x),
    'temas', (select coalesce(json_agg(x order by x.segundos desc, x.questoes desc), '[]') from (
        select t.materia_id, m.materia, m.periodo, m.disciplina,
          (select coalesce(sum(segundos), 0) from ac where ac.materia_id = t.materia_id) as segundos,
          (select coalesce(json_object_agg(aba, seg), '{}') from (select aba, sum(segundos) as seg from ac where ac.materia_id = t.materia_id group by aba) z) as por_aba,
          (select max(valor) from ev where ev.tipo = 'leitura' and ev.materia_id = t.materia_id) as leu_pct,
          (select count(*) from ev where ev.tipo = 'q' and ev.materia_id = t.materia_id) as questoes,
          (select count(*) from ev where ev.tipo = 'q' and ev.materia_id = t.materia_id and acertou) as certas,
          (select count(*) from ev where ev.tipo = 'q' and ev.materia_id = t.materia_id and acertou = false) as erradas,
          (select count(*) from ev where ev.tipo = 'fc' and ev.materia_id = t.materia_id) as flashcards
        from mids t left join materias m on m.id = t.materia_id) x),
    'leituras', (select coalesce(json_agg(x order by x.em), '[]') from (
        select ev.em, ev.valor as pct, ev.resposta as aba, ev.extra ->> 'secao' as secao, m.materia
        from ev left join materias m on m.id = ev.materia_id where ev.tipo = 'leitura') x),
    'questoes', (select coalesce(json_agg(x order by x.em), '[]') from (
        select ev.em, ev.item_id, ev.acertou, ev.resposta, ev.extra ->> 'gabarito' as gabarito_na_hora,
          (select count(*) from eventos y where y.user_id = p_user and y.tipo = 'q' and y.item_id = ev.item_id and y.em <= ev.em) as tentativa,
          q.enunciado, q.alternativas, q.gabarito, q.origem, q.extras ->> 'prova_nome' as prova, m.materia, m.periodo,
          exists (select 1 from ev z where z.tipo = 'estudo_q' and z.item_id = ev.item_id and z.em >= ev.em) as foi_estudar
        from ev left join questoes q on q.id = ev.item_id left join materias m on m.id = ev.materia_id where ev.tipo = 'q') x),
    'flashcards', (select coalesce(json_agg(x order by x.em), '[]') from (
        select ev.em, ev.item_id, ev.acertou, ev.resposta, ev.extra ->> 'estado' as estado,
          (select count(*) from eventos y where y.user_id = p_user and y.tipo = 'fc' and y.item_id = ev.item_id and y.em <= ev.em) as vez,
          f.frente, f.verso, m.materia, m.periodo
        from ev left join flashcards f on f.id = ev.item_id left join materias m on m.id = ev.materia_id where ev.tipo = 'fc') x),
    'osce', (select coalesce(json_agg(x order by x.em), '[]') from (
        select ev.em, ev.tipo, ev.valor as nota, m.materia,
          (select o.id from osce_registros o where o.user_id = p_user and o.tipo = case ev.tipo when 'osce_sim' then 'simulacao' else 'treino' end
             and abs(extract(epoch from (o.em - ev.em))) < 180 order by abs(extract(epoch from (o.em - ev.em))) limit 1) as registro_id,
          (select o.estacao from osce_registros o where o.user_id = p_user and o.tipo = case ev.tipo when 'osce_sim' then 'simulacao' else 'treino' end
             and abs(extract(epoch from (o.em - ev.em))) < 180 order by abs(extract(epoch from (o.em - ev.em))) limit 1) as estacao
        from ev left join materias m on m.id = ev.materia_id where ev.tipo in ('osce_sim', 'osce_prova')) x),
    'criados', (select coalesce(json_agg(x order by x.em), '[]') from (
        select ev.em, ev.tipo, ev.extra from ev where ev.tipo in ('material', 'osce_criado')) x),
    'ia', (select coalesce(json_object_agg(k, n), '{}') from (
        select coalesce(u.uso, 'outro') || ':' || coalesce(u.tarefa, '') as k, count(*) as n from uso_ia u
        where u.pediu = p_user and u.em >= ini and u.em < fim and u.ok group by 1) z)
  ) into r;
  return r;
end $$;
revoke all on function admin_aluno_dia(uuid, date) from public, anon;
grant execute on function admin_aluno_dia(uuid, date) to authenticated;

-- quem estudou num dia e o quê (relatório geral)
create or replace function admin_turma_dia(p_dia date, p_turma uuid default null) returns json
language plpgsql stable security definer set search_path = public as $$
declare ini timestamptz := p_dia::timestamp at time zone 'America/Sao_Paulo';
        fim timestamptz := (p_dia + 1)::timestamp at time zone 'America/Sao_Paulo'; r json;
begin
  if not eh_admin() then raise exception 'Só o administrador.'; end if;
  with quem as (
    select u.id, u.email::text as email, coalesce(u.raw_user_meta_data ->> 'nome', u.raw_user_meta_data ->> 'full_name') as nome from auth.users u
    where rel_conta_ok(u.id)
      and (p_turma is null or exists (select 1 from turma_membros t where t.turma_id = p_turma and t.user_id = u.id and t.status = 'ativo'))),
  ac as (select a.* from acessos a join quem on quem.id = a.user_id where a.inicio >= ini and a.inicio < fim and a.segundos > 0),
  ev as (select e.* from eventos e join quem on quem.id = e.user_id where e.em >= ini and e.em < fim),
  an as (select user_id, id from meus_estudos where tipo = 'caso' and criado_em >= ini and criado_em < fim and user_id in (select id from quem)
         union select user_id, item_id from ev where tipo = 'anamnese' and item_id is not null),
  ativos as (select user_id from ac union select user_id from ev union select user_id from an)
  select coalesce(json_agg(x order by x.segundos desc, x.questoes desc), '[]') into r from (
    select quem.id, quem.nome, quem.email,
      (select coalesce(sum(segundos), 0) from ac where ac.user_id = quem.id) as segundos,
      (select count(*) from ac where ac.user_id = quem.id) as telas,
      (select min(inicio) from ac where ac.user_id = quem.id) as primeiro,
      (select max(inicio + make_interval(secs => segundos)) from ac where ac.user_id = quem.id) as ultimo,
      (select count(*) from ev where ev.user_id = quem.id and tipo = 'q') as questoes,
      (select count(*) from ev where ev.user_id = quem.id and tipo = 'q' and acertou) as certas,
      (select count(*) from ev where ev.user_id = quem.id and tipo = 'q' and acertou = false) as erradas,
      (select count(*) from ev where ev.user_id = quem.id and tipo = 'fc') as flashcards,
      (select count(*) from ev where ev.user_id = quem.id and tipo in ('osce_sim', 'osce_prova')) as osce,
      (select count(*) from an where an.user_id = quem.id) as anamneses,
      (select count(distinct materia_id) from ev where ev.user_id = quem.id and tipo = 'leitura') as lidos,
      (select coalesce(json_agg(distinct m.materia), '[]') from materias m where m.id in (
         select materia_id from ac where ac.user_id = quem.id union select materia_id from ev where ev.user_id = quem.id)) as temas
    from quem where quem.id in (select user_id from ativos)) x;
  return r;
end $$;
revoke all on function admin_turma_dia(date, uuid) from public, anon;
grant execute on function admin_turma_dia(date, uuid) to authenticated;

-- relatório geral: cada aluno com o nome, cada dia da turma, temas, questões mais erradas, horários, aparelhos e desde
-- quando cada tipo de dado é registrado
create or replace function admin_geral(dias int default 180, p_turma uuid default null) returns json
language plpgsql stable security definer set search_path = public as $$
declare desde timestamptz := now() - make_interval(days => least(greatest(dias, 7), 730)); r json;
begin
  if not eh_admin() then raise exception 'Só o administrador.'; end if;
  with
  quem as (
    select u.id, u.email::text as email, coalesce(u.raw_user_meta_data ->> 'nome', u.raw_user_meta_data ->> 'full_name') as nome, u.created_at from auth.users u
    where rel_conta_ok(u.id)
      and (p_turma is null or exists (select 1 from turma_membros t where t.turma_id = p_turma and t.user_id = u.id and t.status = 'ativo'))),
  ac as (select a.user_id, a.materia_id, a.aba, a.inicio, a.segundos, a.aparelho, (a.inicio at time zone 'America/Sao_Paulo') as local
         from acessos a join quem on quem.id = a.user_id where a.inicio >= desde and a.segundos > 0),
  ev as (select e.user_id, e.tipo, e.item_id, e.materia_id, e.acertou, e.valor, e.resposta, e.em, (e.em at time zone 'America/Sao_Paulo')::date as dia,
           row_number() over (partition by e.user_id, e.tipo, e.item_id order by e.em) as tentativa
         from eventos e join quem on quem.id = e.user_id where e.em >= desde),
  an as (select user_id, id, (criado_em at time zone 'America/Sao_Paulo')::date as dia from meus_estudos
         where tipo = 'caso' and criado_em >= desde and user_id in (select id from quem)
         union select user_id, item_id, dia from ev where tipo = 'anamnese' and item_id is not null),
  oc as (select user_id, id from meus_estudos where tipo = 'osce' and criado_em >= desde and user_id in (select id from quem)
         union select user_id, item_id from ev where tipo = 'osce_criado' and item_id is not null),
  diasU as (select user_id, local::date as dia from ac union select user_id, dia from ev union select user_id, dia from an),
  acU as (select user_id, sum(segundos) as segundos, count(*) as telas, max(inicio) as ultimo, min(inicio) as primeiro,
                count(distinct materia_id) filter (where aba in ('conteudo', 'resumo', 'original')) as abertos from ac group by user_id),
  evU as (select user_id, count(*) filter (where tipo = 'q') as respostas, count(distinct item_id) filter (where tipo = 'q') as questoes,
                round(100.0 * avg(case when acertou then 1 else 0 end) filter (where tipo = 'q' and tentativa = 1 and acertou is not null)) as acerto_1a,
                round(100.0 * avg(case when acertou then 1 else 0 end) filter (where tipo = 'q' and acertou is not null)) as acerto,
                count(*) filter (where tipo = 'fc') as flashcards, count(distinct item_id) filter (where tipo = 'fc') as flashcards_unicos,
                count(*) filter (where tipo in ('osce_sim', 'osce_prova')) as osce, round(avg(valor) filter (where tipo in ('osce_sim', 'osce_prova')), 1) as osce_media,
                count(distinct materia_id) filter (where tipo = 'leitura') as lidos, count(*) filter (where tipo = 'material') as materiais_criados,
                max(em) as ultimo, min(em) as primeiro from ev group by user_id),
  temU as (select user_id, count(distinct materia_id) as temas from (select user_id, materia_id from ac union select user_id, materia_id from ev) z
           where materia_id is not null group by user_id),
  diaN as (select user_id, count(distinct dia) as dias from diasU group by user_id),
  anU as (select user_id, count(*) as n from an group by user_id),
  ocU as (select user_id, count(*) as n from oc group by user_id),
  iaU as (select u.pediu as user_id, count(*) as n from uso_ia u where u.em >= desde and u.ok and u.uso = 'estudo' and u.pediu in (select id from quem) group by u.pediu),
  alunos as (
    select quem.id, quem.nome, quem.email, quem.created_at as conta_criada, diaN.dias,
      coalesce(acU.segundos, 0) as segundos, coalesce(acU.telas, 0) as telas, coalesce(temU.temas, 0) as temas, coalesce(acU.abertos, 0) as abertos,
      coalesce(evU.lidos, 0) as lidos, coalesce(evU.respostas, 0) as respostas, coalesce(evU.questoes, 0) as questoes, evU.acerto_1a, evU.acerto,
      coalesce(evU.flashcards, 0) as flashcards, coalesce(evU.flashcards_unicos, 0) as flashcards_unicos, coalesce(evU.osce, 0) as osce, evU.osce_media,
      coalesce(anU.n, 0) as anamneses, coalesce(ocU.n, 0) as osce_criados, coalesce(evU.materiais_criados, 0) as materiais_criados, coalesce(iaU.n, 0) as ia,
      (select c.aceitou from consentimentos c where c.user_id = quem.id) as consentiu,
      greatest(acU.ultimo, evU.ultimo) as ultimo, least(acU.primeiro, evU.primeiro) as primeiro
    from quem join diaN on diaN.user_id = quem.id
    left join acU on acU.user_id = quem.id left join evU on evU.user_id = quem.id left join temU on temU.user_id = quem.id
    left join anU on anU.user_id = quem.id left join ocU on ocU.user_id = quem.id left join iaU on iaU.user_id = quem.id),
  porDia as (
    select u.dia, u.alunos, coalesce(a.seg, 0) as segundos, coalesce(e.q, 0) as questoes, e.acerto, coalesce(e.fc, 0) as flashcards,
           coalesce(e.osce, 0) as osce, coalesce(n.n, 0) as anamneses
    from (select dia, count(distinct user_id) as alunos from diasU group by dia) u
    left join (select local::date as dia, sum(segundos) as seg from ac group by 1) a on a.dia = u.dia
    left join (select dia, count(*) filter (where tipo = 'q') as q, round(100.0 * avg(case when acertou then 1 else 0 end) filter (where tipo = 'q' and acertou is not null)) as acerto,
                      count(*) filter (where tipo = 'fc') as fc, count(*) filter (where tipo in ('osce_sim', 'osce_prova')) as osce from ev group by dia) e on e.dia = u.dia
    left join (select dia, count(*) as n from an group by dia) n on n.dia = u.dia),
  temas as (
    select t.materia_id, m.materia, m.periodo, m.disciplina,
      count(distinct t.user_id) as alunos, coalesce(sum(t.seg), 0) as segundos, sum(t.q) as questoes,
      round(100.0 * sum(t.certas) / nullif(sum(t.q_com_gab), 0)) as acerto
    from (select user_id, materia_id, segundos as seg, 0 as q, 0 as certas, 0 as q_com_gab from ac where materia_id is not null
          union all select user_id, materia_id, 0, case when tipo = 'q' then 1 else 0 end, case when tipo = 'q' and acertou then 1 else 0 end,
                           case when tipo = 'q' and acertou is not null then 1 else 0 end from ev where materia_id is not null) t
    left join materias m on m.id = t.materia_id group by t.materia_id, m.materia, m.periodo, m.disciplina),
  dificeis as (
    select ev.item_id, count(distinct ev.user_id) as alunos, count(*) as respostas,
      round(100.0 * avg(case when ev.acertou then 1 else 0 end)) as acerto_1a
    from ev where ev.tipo = 'q' and ev.tentativa = 1 and ev.acertou is not null group by ev.item_id having count(distinct ev.user_id) >= 3)
  select json_build_object(
    'desde', desde,
    'totais', json_build_object(
      'alunos', (select count(*) from alunos), 'segundos', (select coalesce(sum(segundos), 0) from ac),
      'dias_estudo', (select count(*) from diasU), 'telas', (select count(*) from ac),
      'respostas', (select count(*) from ev where tipo = 'q'), 'questoes', (select count(*) from (select distinct user_id, item_id from ev where tipo = 'q') z),
      'acerto', (select round(100.0 * avg(case when acertou then 1 else 0 end)) from ev where tipo = 'q' and acertou is not null),
      'acerto_1a', (select round(100.0 * avg(case when acertou then 1 else 0 end)) from ev where tipo = 'q' and tentativa = 1 and acertou is not null),
      'flashcards', (select count(*) from ev where tipo = 'fc'),
      'osce', (select count(*) from ev where tipo in ('osce_sim', 'osce_prova')),
      'osce_media', (select round(avg(valor), 1) from ev where tipo in ('osce_sim', 'osce_prova')),
      'anamneses', (select count(*) from an), 'osce_criados', (select count(*) from oc),
      'materiais_criados', (select count(*) from ev where tipo = 'material'),
      'lidos', (select count(*) from (select distinct user_id, materia_id from ev where tipo = 'leitura') z),
      'abertos', (select count(*) from (select distinct user_id, materia_id from ac where aba in ('conteudo', 'resumo', 'original')) z)),
    'alunos', (select coalesce(json_agg(a order by a.segundos desc, a.respostas desc), '[]') from alunos a),
    'por_dia', (select coalesce(json_agg(d order by d.dia), '[]') from porDia d),
    'temas', (select coalesce(json_agg(t order by t.segundos desc, t.questoes desc), '[]') from (select * from temas order by segundos desc, questoes desc limit 80) t),
    'dificeis', (select coalesce(json_agg(x order by x.acerto_1a, x.alunos desc), '[]') from (
        select d.*, left(q.enunciado, 300) as enunciado, m.materia, m.periodo from dificeis d
        left join questoes q on q.id = d.item_id left join materias m on m.id = q.materia_id order by d.acerto_1a, d.alunos desc limit 40) x),
    'abas', (select coalesce(json_object_agg(aba, seg), '{}') from (select coalesce(aba, '') as aba, sum(segundos) as seg from ac group by 1) z),
    'horas', (select coalesce(json_object_agg(h, seg), '{}') from (select extract(hour from local)::int as h, sum(segundos) as seg from ac group by 1) z),
    'semana', (select coalesce(json_object_agg(d, seg), '{}') from (select extract(isodow from local)::int as d, sum(segundos) as seg from ac group by 1) z),
    'aparelhos', (select coalesce(json_object_agg(k, n), '{}') from (select split_part(aparelho, ' · ', 1) as k, count(distinct user_id) as n from ac where aparelho is not null group by 1) z),
    'consentimento', json_build_object('sim', (select count(*) from alunos where consentiu), 'nao', (select count(*) from alunos where consentiu = false),
      'sem_resposta', (select count(*) from alunos where consentiu is null)),
    'registrado_desde', json_build_object(
      'tempo', (select min(a.inicio) from acessos a join quem on quem.id = a.user_id),
      'questoes', (select min(e.em) from eventos e join quem on quem.id = e.user_id where e.tipo = 'q'),
      'resposta_marcada', (select min(e.em) from eventos e join quem on quem.id = e.user_id where e.tipo = 'q' and e.resposta is not null),
      'leitura', (select min(e.em) from eventos e join quem on quem.id = e.user_id where e.tipo = 'leitura'),
      'osce_nota', (select min(e.em) from eventos e join quem on quem.id = e.user_id where e.tipo in ('osce_sim', 'osce_prova')),
      'osce_completo', (select min(o.em) from osce_registros o join quem on quem.id = o.user_id),
      'anamneses', (select min(m.criado_em) from meus_estudos m join quem on quem.id = m.user_id where m.tipo = 'caso')),
    'excluidos', (select coalesce(json_agg(x order by x.em desc), '[]') from (
        select x.user_id as id, u.email::text as email, coalesce(u.raw_user_meta_data ->> 'nome', u.raw_user_meta_data ->> 'full_name') as nome, x.em
        from relatorio_excluidos x left join auth.users u on u.id = x.user_id) x)
  ) into r;
  return r;
end $$;
revoke all on function admin_geral(int, uuid) from public, anon;
grant execute on function admin_geral(int, uuid) to authenticated;

-- a ficha de cada aluno (refeita do v42: mais OSCE, anamneses, leitura, autorização e desde quando cada dado é registrado)
create or replace function admin_aluno(p_user uuid, dias int default 90) returns json
language plpgsql stable security definer set search_path = public as $$
declare desde timestamptz := now() - make_interval(days => least(greatest(dias, 7), 730)); r json;
begin
  if not eh_admin() then raise exception 'Só o administrador.'; end if;
  with
  ac as (
    select a.materia_id, a.aba, a.inicio, a.segundos, (a.inicio at time zone 'America/Sao_Paulo')::date as dia
    from acessos a where a.user_id = p_user and a.inicio >= desde and a.segundos > 0),
  ev as (
    select e.tipo, e.item_id, e.materia_id, e.acertou, e.em, e.valor, (e.em at time zone 'America/Sao_Paulo')::date as dia,
           row_number() over (partition by e.tipo, e.item_id order by e.em) as tentativa,
           count(*) over (partition by e.tipo, e.item_id) as vezes
    from eventos e where e.user_id = p_user and e.em >= desde),
  an as (select (criado_em at time zone 'America/Sao_Paulo')::date as dia, id from meus_estudos where user_id = p_user and tipo = 'caso' and criado_em >= desde
         union select dia, item_id from ev where tipo = 'anamnese' and item_id is not null),
  oc as (select id from meus_estudos where user_id = p_user and tipo = 'osce' and criado_em >= desde
         union select item_id from ev where tipo = 'osce_criado' and item_id is not null),
  -- cada questão: a primeira e a última resposta, quantas vezes fez, se errou e depois acertou, se foi estudar depois do erro
  qs as (
    select q.item_id, max(q.materia_id::text)::uuid as materia_id, count(*) as vezes, min(q.em) as primeira_em, max(q.em) as ultima_em,
      bool_or(q.acertou) filter (where q.tentativa = 1) as acertou_1a,
      (array_agg(q.acertou order by q.em desc))[1] as acertou_ultima,
      bool_or(q.acertou) filter (where q.tentativa > 1) as acertou_depois
    from ev q where q.tipo = 'q' and q.item_id is not null group by q.item_id),
  qs2 as (
    select qs.*, (qs.acertou_1a is not true and qs.acertou_depois is true) as recuperou,
      (qs.acertou_1a is not true and (
        exists (select 1 from ev x where x.tipo = 'estudo_q' and x.item_id = qs.item_id)
        or exists (select 1 from ac where ac.materia_id = qs.materia_id and ac.aba in ('conteudo', 'resumo', 'original')
                   and ac.inicio between qs.primeira_em and qs.primeira_em + interval '30 minutes'))) as estudou
    from qs),
  porDia as (
    select d.dia, coalesce(a.seg, 0) as segundos, coalesce(a.telas, 0) as telas,
           coalesce(e.q, 0) as questoes, coalesce(e.certas, 0) as certas, coalesce(e.erradas, 0) as erradas, coalesce(e.fc, 0) as flashcards,
           coalesce(e.osce, 0) as osce, coalesce(e.lidos, 0) as lidos, (select count(*) from an where an.dia = d.dia) as anamneses,
           (select coalesce(json_agg(distinct m.materia), '[]') from materias m where m.id = any(coalesce(a.mids, '{}') || coalesce(e.mids, '{}'))) as temas
    from (select dia from ac union select dia from ev union select dia from an) d
    left join (select dia, sum(segundos) as seg, count(*) as telas, array_agg(distinct materia_id) filter (where materia_id is not null) as mids from ac group by dia) a on a.dia = d.dia
    left join (select dia, count(*) filter (where tipo = 'q') as q, count(*) filter (where tipo = 'q' and acertou) as certas,
                      count(*) filter (where tipo = 'q' and acertou = false) as erradas, count(*) filter (where tipo = 'fc') as fc,
                      count(*) filter (where tipo in ('osce_sim', 'osce_prova')) as osce, count(distinct materia_id) filter (where tipo = 'leitura') as lidos,
                      array_agg(distinct materia_id) filter (where materia_id is not null) as mids
               from ev group by dia) e on e.dia = d.dia),
  temas as (
    select t.materia_id, m.materia, m.periodo, m.disciplina,
      (select coalesce(sum(segundos), 0) from ac where ac.materia_id = t.materia_id) as segundos,
      (select count(*) from ac where ac.materia_id = t.materia_id) as visitas,
      (select coalesce(json_object_agg(aba, seg), '{}') from (select aba, sum(segundos) as seg from ac where ac.materia_id = t.materia_id group by aba) z) as por_aba,
      (select count(*) from qs2 where qs2.materia_id = t.materia_id) as questoes,
      (select count(*) from qs2 where qs2.materia_id = t.materia_id and acertou_1a) as certas_1a,
      (select count(*) from qs2 where qs2.materia_id = t.materia_id and acertou_1a is not true) as erradas_1a,
      (select count(*) from qs2 where qs2.materia_id = t.materia_id and vezes > 1) as refeitas,
      (select count(*) from qs2 where qs2.materia_id = t.materia_id and recuperou) as recuperadas,
      (select count(*) from ev where ev.tipo = 'fc' and ev.materia_id = t.materia_id) as flashcards,
      (select nullif(p.resposta, '')::jsonb ->> 'pct' from progresso p where p.user_id = p_user and p.tipo = 'leitura' and p.materia_id = t.materia_id order by p.atualizado_em desc limit 1) as leitura_pct,
      greatest((select max(inicio) from ac where ac.materia_id = t.materia_id), (select max(em) from ev where ev.materia_id = t.materia_id)) as ultima
    from (select materia_id from ac where materia_id is not null union select materia_id from ev where materia_id is not null) t
    left join materias m on m.id = t.materia_id),
  semanas as (
    select s.sem, coalesce(a.min, 0) as minutos, coalesce(e.q, 0) as questoes, e.acerto
    from (select distinct date_trunc('week', dia)::date as sem from porDia) s
    left join (select date_trunc('week', dia)::date as sem, round(sum(segundos) / 60.0) as min from ac group by 1) a on a.sem = s.sem
    left join (select date_trunc('week', dia)::date as sem, count(*) as q, round(100.0 * avg(case when acertou then 1 else 0 end)) as acerto
               from ev where tipo = 'q' and acertou is not null group by 1) e on e.sem = s.sem)
  select json_build_object(
    'desde', desde,
    'resumo', json_build_object(
      'dias_ativos', (select count(*) from porDia),
      'segundos', (select coalesce(sum(segundos), 0) from ac),
      'telas', (select count(*) from ac),
      'primeiro', (select min(inicio) from ac), 'ultimo', (select max(inicio) from ac),
      'questoes_respostas', (select count(*) from ev where tipo = 'q'),
      'questoes_unicas', (select count(*) from qs2),
      'certas_1a', (select count(*) from qs2 where acertou_1a), 'erradas_1a', (select count(*) from qs2 where acertou_1a is not true),
      'refeitas', (select count(*) from qs2 where vezes > 1), 'recuperadas', (select count(*) from qs2 where recuperou),
      'estudou_apos_erro', (select count(*) from qs2 where estudou),
      'acerto_refeitas', (select round(100.0 * avg(case when acertou then 1 else 0 end)) from ev where tipo = 'q' and tentativa > 1 and acertou is not null),
      'flashcards', (select count(*) from ev where tipo = 'fc'), 'flashcards_unicos', (select count(distinct item_id) from ev where tipo = 'fc'),
      'temas', (select count(*) from temas),
      'abertos', (select count(distinct materia_id) from ac where aba in ('conteudo', 'resumo', 'original')),
      'lidos', (select count(distinct materia_id) from ev where tipo = 'leitura'),
      'osce', (select count(*) from ev where tipo in ('osce_sim', 'osce_prova')),
      'osce_media', (select round(avg(valor), 1) from ev where tipo in ('osce_sim', 'osce_prova')),
      'anamneses', (select count(*) from an), 'osce_criados', (select count(*) from oc),
      'materiais_criados', (select count(*) from ev where tipo = 'material'),
      'ia_perguntas', (select count(*) from uso_ia u where u.pediu = p_user and u.em >= desde and u.ok and u.uso = 'estudo')),
    'por_dia', (select coalesce(json_agg(d order by d.dia desc), '[]') from porDia d),
    'semanas', (select coalesce(json_agg(s order by s.sem), '[]') from semanas s),
    'temas', (select coalesce(json_agg(t order by t.segundos desc, t.questoes desc), '[]') from temas t),
    'questoes', (select coalesce(json_agg(x order by x.ultima_em desc), '[]') from (
        select qs2.item_id, qs2.vezes, qs2.primeira_em, qs2.ultima_em, qs2.acertou_1a, qs2.acertou_ultima, qs2.recuperou, qs2.estudou,
               left(q.enunciado, 220) as enunciado, q.origem, q.extras ->> 'prova_nome' as prova, m.materia, m.periodo
        from qs2 left join questoes q on q.id = qs2.item_id left join materias m on m.id = qs2.materia_id
        order by qs2.ultima_em desc limit 1500) x),
    'flashcards_estado', (select coalesce(json_object_agg(coalesce(estado, 'sem estado'), n), '{}') from (
        select p.estado, count(*) as n from progresso p where p.user_id = p_user and p.tipo = 'fc' group by p.estado) z),
    'ferramentas', (select coalesce(json_object_agg(tipo, n), '{}') from (
        select tipo, count(*) as n from usos_recurso where user_id = p_user and em >= desde group by tipo) z),
    'simulacoes', (select coalesce(json_agg(x order by x.em desc), '[]') from (
        select e.tipo, e.em, e.valor as nota, m.materia from ev e left join materias m on m.id = e.materia_id
        where e.tipo in ('osce_sim', 'osce_prova') order by e.em desc limit 100) x),
    -- das anamneses, só a data (o título já diz do caso, e o conteúdo é só do aluno)
    'estudos', (select coalesce(json_agg(x order by x.criado_em desc), '[]') from (
        select tipo, case when tipo = 'caso' then null else titulo end as titulo, criado_em from meus_estudos where user_id = p_user and criado_em >= desde order by criado_em desc limit 100) x),
    'osce_registros', (select coalesce(json_agg(x order by x.em desc), '[]') from (
        select o.id, o.tipo, o.em, o.estacao, o.nota, o.itens_feitos, o.itens_total, o.duracao_seg, m.materia
        from osce_registros o left join materias m on m.id = o.materia_id where o.user_id = p_user and o.em >= desde order by o.em desc limit 300) x),
    'pessoa', (select json_build_object('email', u.email::text, 'nome', coalesce(u.raw_user_meta_data ->> 'nome', u.raw_user_meta_data ->> 'full_name'),
        'criado_em', u.created_at, 'ultimo_login', u.last_sign_in_at,
        'fora', exists (select 1 from relatorio_excluidos x where x.user_id = u.id),
        'admin', exists (select 1 from admins a where lower(a.email) = lower(u.email)),
        'consentiu', (select c.aceitou from consentimentos c where c.user_id = u.id), 'consentiu_em', (select c.em from consentimentos c where c.user_id = u.id),
        'turmas', (select coalesce(json_agg(t.nome), '[]') from turma_membros tm join turmas t on t.id = tm.turma_id where tm.user_id = u.id and tm.status = 'ativo'))
      from auth.users u where u.id = p_user),
    'registrado_desde', json_build_object(
      'tempo', (select min(inicio) from acessos where user_id = p_user),
      'resposta_marcada', (select min(em) from eventos where user_id = p_user and tipo = 'q' and resposta is not null),
      'leitura', (select min(em) from eventos where user_id = p_user and tipo = 'leitura'),
      'osce_completo', (select min(em) from osce_registros where user_id = p_user)),
    'avaliacoes', (select coalesce(json_agg(x order by x.em desc), '[]') from (select nota, comentario, em from avaliacoes_app where user_id = p_user order by em desc limit 20) x)
  ) into r;
  return r;
end $$;
revoke all on function admin_aluno(uuid, int) from public, anon;
grant execute on function admin_aluno(uuid, int) to authenticated;

-- relatório de uso e aprendizado e lista dos alunos (do v41 e v42): sem as contas tiradas dos relatórios
create or replace function admin_impacto(dias int default 180, p_turma uuid default null) returns json
language plpgsql stable security definer set search_path = public as $$
declare desde timestamptz := now() - make_interval(days => least(greatest(dias, 14), 730)); r json;
begin
  if not eh_admin() then raise exception 'Só o administrador.'; end if;
  with
  quem as (   -- os alunos (sem os administradores; o robô não registra uso); numa turma, só os dela
    select u.id from auth.users u
    where rel_conta_ok(u.id)
      and (p_turma is null or exists (select 1 from turma_membros t where t.turma_id = p_turma and t.user_id = u.id and t.status = 'ativo'))),
  ac as (
    select a.user_id, date_trunc('week', a.inicio at time zone 'America/Sao_Paulo')::date as sem,
           (a.inicio at time zone 'America/Sao_Paulo')::date as dia, a.segundos
    from acessos a join quem on quem.id = a.user_id where a.inicio >= desde and a.segundos > 0),
  ev as (
    select e.user_id, e.tipo, e.item_id, e.acertou, e.em, date_trunc('week', e.em at time zone 'America/Sao_Paulo')::date as sem,
           row_number() over (partition by e.user_id, e.tipo, e.item_id order by e.em) as tentativa,
           row_number() over (partition by e.user_id, e.tipo order by e.em) as ordem,
           count(*) over (partition by e.user_id, e.tipo) as total
    from eventos e join quem on quem.id = e.user_id where e.em >= desde and e.tipo in ('q', 'fc')),
  semAc as (select sem, round(sum(segundos) / 60.0) as minutos from ac group by sem),
  semEv as (select sem, count(*) filter (where tipo = 'q') as questoes, count(*) filter (where tipo = 'fc') as flashcards,
              round(100.0 * avg(case when acertou then 1 else 0 end) filter (where tipo = 'q' and acertou is not null)) as acerto from ev group by sem),
  semU as (select sem, count(distinct user_id) as alunos from (select user_id, sem from ac union select user_id, sem from ev) z group by sem),
  semanas as (
    select u.sem, u.alunos, coalesce(a.minutos, 0) as minutos, coalesce(e.questoes, 0) as questoes, e.acerto, coalesce(e.flashcards, 0) as flashcards
    from semU u left join semAc a on a.sem = u.sem left join semEv e on e.sem = u.sem),
  tentativas as (
    select least(tentativa, 3) as t, count(*) as n, round(100.0 * avg(case when acertou then 1 else 0 end)) as acerto
    from ev where tipo = 'q' and acertou is not null group by 1),
  itens as (   -- cada questão que o aluno errou na primeira vez: virou acerto depois? em quantos dias?
    select user_id, item_id,
      bool_or(acertou) filter (where tentativa > 1) as recuperou,
      extract(epoch from (min(em) filter (where tentativa > 1 and acertou) - min(em))) / 86400.0 as ndias
    from ev where tipo = 'q' group by user_id, item_id
    having bool_and(acertou is not true) filter (where tentativa = 1)),
  porAluno as (   -- antes e depois: as 20 primeiras questões contra as 20 últimas (alunos com 40 ou mais)
    select user_id,
      avg(case when acertou then 1.0 else 0 end) filter (where ordem <= 20) as antes,
      avg(case when acertou then 1.0 else 0 end) filter (where ordem > total - 20) as depois
    from ev where tipo = 'q' and acertou is not null and total >= 40 group by user_id),
  semAluno as (select user_id, sem, sum(segundos) / 60.0 as min from ac group by user_id, sem),
  tempoAluno as (   -- tempo por semana: as 2 primeiras semanas de uso contra as 2 últimas (alunos com 4 semanas ou mais)
    select user_id, avg(min) filter (where k <= 2) as inicio, avg(min) filter (where k > n - 2) as fim
    from (select user_id, min, row_number() over (partition by user_id order by sem) as k, count(*) over (partition by user_id) as n from semAluno) z
    where n >= 4 group by user_id),
  volta as (   -- de quem estudou numa semana, quantos voltaram na semana seguinte
    select a.sem, count(distinct a.user_id) as n, count(distinct b.user_id) as voltaram
    from (select distinct user_id, sem from ac) a left join (select distinct user_id, sem from ac) b on b.user_id = a.user_id and b.sem = a.sem + 7
    where a.sem + 7 <= date_trunc('week', now() at time zone 'America/Sao_Paulo')::date - 7 group by a.sem),
  aval as (select distinct on (v.user_id) v.user_id, v.nota, v.comentario, v.em from avaliacoes_app v join quem on quem.id = v.user_id where v.em >= desde order by v.user_id, v.em desc)
  select json_build_object(
    'desde', desde,
    'totais', json_build_object(
      'alunos', (select count(distinct user_id) from (select user_id from ac union select user_id from ev) z),
      'minutos', (select round(coalesce(sum(segundos), 0) / 60.0) from ac),
      'dias_estudo', (select count(*) from (select distinct user_id, dia from ac) z),
      'questoes', (select count(*) from ev where tipo = 'q'),
      'flashcards', (select count(*) from ev where tipo = 'fc'),
      'acerto', (select round(100.0 * avg(case when acertou then 1 else 0 end)) from ev where tipo = 'q' and acertou is not null)),
    'semanas', (select coalesce(json_agg(x order by x.sem), '[]') from semanas x),
    'tentativas', (select coalesce(json_agg(x order by x.t), '[]') from tentativas x),
    'recuperacao', json_build_object('erros', (select count(*) from itens), 'recuperados', (select count(*) from itens where recuperou),
      'dias_mediana', (select round((percentile_cont(0.5) within group (order by ndias))::numeric, 1) from itens where recuperou and ndias is not null)),
    'antes_depois', json_build_object('alunos', (select count(*) from porAluno), 'antes', (select round(100 * avg(antes)) from porAluno),
      'depois', (select round(100 * avg(depois)) from porAluno), 'melhoraram', (select count(*) from porAluno where depois > antes)),
    'tempo', json_build_object('alunos', (select count(*) from tempoAluno), 'inicio', (select round(avg(inicio)) from tempoAluno),
      'fim', (select round(avg(fim)) from tempoAluno), 'aumentaram', (select count(*) from tempoAluno where fim > inicio)),
    'retencao', (select round(100.0 * sum(voltaram) / nullif(sum(n), 0)) from volta),
    'avaliacoes', json_build_object('n', (select count(*) from aval), 'media', (select round(avg(nota), 1) from aval),
      'promotores', (select count(*) from aval where nota >= 9), 'detratores', (select count(*) from aval where nota <= 6),
      'comentarios', (select coalesce(json_agg(json_build_object('nota', nota, 'texto', comentario, 'em', em) order by em desc), '[]')
                      from (select * from aval where coalesce(trim(comentario), '') <> '' order by em desc limit 40) c))
  ) into r;
  return r;
end $$;
revoke all on function admin_impacto(int, uuid) from public, anon;
grant execute on function admin_impacto(int, uuid) to authenticated;

create or replace function admin_alunos(dias int default 90, p_turma uuid default null) returns json
language plpgsql stable security definer set search_path = public as $$
declare desde timestamptz := now() - make_interval(days => least(greatest(dias, 7), 730)); r json;
begin
  if not eh_admin() then raise exception 'Só o administrador.'; end if;
  with quem as (
    select u.id, u.email::text as email, coalesce(u.raw_user_meta_data ->> 'nome', u.raw_user_meta_data ->> 'full_name') as nome from auth.users u
    where rel_conta_ok(u.id)
      and (p_turma is null or exists (select 1 from turma_membros t where t.turma_id = p_turma and t.user_id = u.id and t.status = 'ativo'))),
  ac as (select user_id, count(distinct (inicio at time zone 'America/Sao_Paulo')::date) as dias, sum(segundos) as seg, max(inicio) as ultimo
         from acessos where inicio >= desde and segundos > 0 group by user_id),
  ev as (select user_id, count(*) filter (where tipo = 'q') as q, round(100.0 * avg(case when acertou then 1 else 0 end) filter (where tipo = 'q' and acertou is not null)) as acerto,
                count(*) filter (where tipo = 'fc') as fc
         from eventos where em >= desde group by user_id)
  select coalesce(json_agg(x order by x.segundos desc nulls last), '[]') into r from (
    select quem.id, quem.email, quem.nome, coalesce(ac.dias, 0) as dias, coalesce(ac.seg, 0) as segundos, ac.ultimo,
           coalesce(ev.q, 0) as questoes, ev.acerto, coalesce(ev.fc, 0) as flashcards
    from quem left join ac on ac.user_id = quem.id left join ev on ev.user_id = quem.id
    where ac.user_id is not null or ev.user_id is not null) x;
  return r;
end $$;
revoke all on function admin_alunos(int, uuid) from public, anon;
grant execute on function admin_alunos(int, uuid) to authenticated;

-- Administração › Pessoas (do v13): "Na turma" conta quem entrou pela turma (antes só o código antigo) e marca as contas tiradas
create or replace function admin_resumo(dias int default 30) returns json
language plpgsql stable security definer set search_path = public as $$
declare desde timestamptz := now() - make_interval(days => dias); r json;
begin
  if not eh_admin() then raise exception 'Apenas o administrador pode ver este painel.'; end if;
  with ac as (
    select a.user_id,
           sum(a.segundos) filter (where a.inicio >= desde) as segundos,
           count(distinct (a.inicio at time zone 'America/Sao_Paulo')::date) filter (where a.inicio >= desde) as dias_ativos,
           max(a.inicio + make_interval(secs => a.segundos)) as ultimo_acesso
    from acessos a group by a.user_id),
  doc as (select d.criado_por as uid, count(*) as n from documentos d group by d.criado_por),
  env as (select e.user_id as uid, count(*) as n from envios e group by e.user_id),
  pr as (
    select p.user_id as uid, count(*) filter (where p.tipo = 'q') as questoes,
           round(100.0 * avg(case when p.acertou then 1 else 0 end) filter (where p.tipo = 'q' and p.acertou is not null)) as acerto,
           count(*) filter (where p.tipo = 'fc') as flashcards
    from progresso p group by p.user_id),
  cr as (
    select z.criado_por as uid, count(*) as n from (
      select f.criado_por from flashcards f where f.origem = 'ALUNO'
      union all select q.criado_por from questoes q where q.origem = 'ALUNO') z group by z.criado_por)
  select coalesce(json_agg(x order by x.ultimo_login desc nulls last), '[]') into r from (
    select u.id, u.email::text as email, u.created_at as criado_em, u.last_sign_in_at as ultimo_login,
      (exists (select 1 from membros m where lower(m.email) = lower(u.email))
        or exists (select 1 from turma_membros t where t.user_id = u.id and t.status = 'ativo')) as membro,
      exists (select 1 from relatorio_excluidos x where x.user_id = u.id) as fora,
      coalesce(ac.segundos, 0) as segundos, coalesce(ac.dias_ativos, 0) as dias_ativos, ac.ultimo_acesso,
      coalesce(doc.n, 0) as arquivos, coalesce(env.n, 0) as envios,
      coalesce(pr.questoes, 0) as questoes, pr.acerto, coalesce(pr.flashcards, 0) as flashcards,
      coalesce(cr.n, 0) as criados
    from auth.users u
    left join ac on ac.user_id = u.id left join doc on doc.uid = u.id left join env on env.uid = u.id
    left join pr on pr.uid = u.id left join cr on cr.uid = u.id) x;
  return r;
end $$;
revoke all on function admin_resumo(int) from public, anon;
grant execute on function admin_resumo(int) to authenticated;

select 'Pronto: relatório completo (v43).' as resultado;
