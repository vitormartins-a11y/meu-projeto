-- v7: registro de uso das IAs, para o painel de cotas da Administração
-- Cada pedido à IA vira uma linha (qual IA respondeu, tokens, se bateu no limite do dia).
-- Quem grava é a função "ia" do servidor; só o administrador lê. A turma não vê nem mexe.
create table if not exists uso_ia (
  id bigserial primary key,
  em timestamptz not null default now(),
  provedor text, modelo text, tarefa text, origem text,
  ok boolean, status int, tentativas int, ms int,
  tokens_in int, tokens_out int,
  dia_gemini boolean default false, dia_groq boolean default false,
  groq_modelo text, groq_limite int, groq_restante int);
create index if not exists uso_ia_em on uso_ia (em);
alter table uso_ia enable row level security;
drop policy if exists ler on uso_ia;
create policy ler on uso_ia for select to authenticated using (eh_admin());

-- Resumo por hora (o painel junta em dias e semanas sem baixar linha por linha)
create or replace function uso_ia_por_hora(desde timestamptz)
returns table (hora timestamptz, provedor text, origem text, aceitos bigint, recusados bigint,
               cota_dia_gemini bigint, cota_dia_groq bigint, tokens_in bigint, tokens_out bigint)
language sql stable security definer set search_path = public as $$
  select date_trunc('hour', em), provedor, origem,
         count(*) filter (where ok), count(*) filter (where not ok),
         count(*) filter (where dia_gemini), count(*) filter (where dia_groq),
         coalesce(sum(tokens_in), 0), coalesce(sum(tokens_out), 0)
  from uso_ia where em >= desde and eh_admin()
  group by 1, 2, 3 order by 1;
$$;
revoke all on function uso_ia_por_hora(timestamptz) from public, anon;
grant execute on function uso_ia_por_hora(timestamptz) to authenticated;
