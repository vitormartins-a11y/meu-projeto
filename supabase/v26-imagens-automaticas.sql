-- v26: imagens dos arquivos sem precisar ir à Administração. Precisa do v23. Pode rodar mais de uma vez.
-- * Cada arquivo guarda quando as imagens dele foram feitas (imagens_em). Arquivo de PDF ou imagem do Drive sem essa
--   data ficou sem imagens (o envio foi interrompido ou deu erro): o robô do computador refaz sozinho.
-- * Antes, "já conferido" ficava só no aparelho de quem conferiu; por isso a lista da Administração nunca zerava
--   (PDFs só de texto, que não têm figura nenhuma, voltavam para a lista em todo aparelho).
-- * O robô pode guardar as imagens nos arquivos enviados por qualquer pessoa da turma (só as imagens e o texto lido).

alter table documentos add column if not exists imagens_em timestamptz;

-- já conferidos: o que não é PDF nem imagem, o que não veio do Drive (não dá para baixar de novo)
-- e os arquivos que já têm alguma imagem
update documentos set imagens_em = coalesce(criado_em, now())
  where imagens_em is null and (tipo is null or tipo not in ('PDF', 'Imagem') or drive_id is null);
update documentos d set imagens_em = coalesce(d.criado_em, now())
  where d.imagens_em is null and exists (
    select 1 from paginas p where p.documento_id = d.id
      and (p.imagem is not null or coalesce(p.figuras, '[]'::jsonb) <> '[]'::jsonb or coalesce(cardinality(p.imagens), 0) > 0));

-- a busca do robô pelos que faltam lê só este índice pequeno
create index if not exists documentos_sem_imagens on documentos (criado_em) where imagens_em is null;

-- guarda as imagens (e o texto lido) das páginas de um arquivo e marca o arquivo como feito.
-- Quem pode: quem enviou o arquivo, o administrador e o robô.
create or replace function guardar_imagens(doc uuid, linhas jsonb) returns int
language plpgsql security definer set search_path = public as $$
declare n int := 0;
begin
  if not exists (select 1 from documentos d where d.id = doc
                 and (eh_admin() or eh_robo() or d.criado_por = auth.uid())) then
    raise exception 'Sem permissão para guardar as imagens deste arquivo.';
  end if;
  if jsonb_typeof(linhas) <> 'array' or jsonb_array_length(linhas) > 2000 then raise exception 'Pedido inválido.'; end if;
  update paginas p set
    imagem = e ->> 'imagem',
    figuras = case when jsonb_typeof(e -> 'figuras') = 'array' then e -> 'figuras' else '[]'::jsonb end,
    titulo = case when e ? 'titulo' then e ->> 'titulo' else p.titulo end,
    texto = case when e ? 'texto' then e ->> 'texto' else p.texto end,
    texto_norm = case when e ? 'texto_norm' then e ->> 'texto_norm' else p.texto_norm end
  from jsonb_array_elements(linhas) e
  where p.documento_id = doc and p.id::text = e ->> 'id';
  get diagnostics n = row_count;
  update documentos set imagens_em = now() where id = doc;
  return n;
end $$;
revoke all on function guardar_imagens(uuid, jsonb) from public, anon;
grant execute on function guardar_imagens(uuid, jsonb) to authenticated;

select 'Pronto: ' || count(*) || ' arquivos ainda sem imagens (o robô refaz sozinho).' as resultado
from documentos where imagens_em is null and tipo in ('PDF', 'Imagem') and drive_id is not null;
