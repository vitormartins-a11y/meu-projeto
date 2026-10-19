-- v35: organizar pelo Drive também arruma os áudios e vídeos que ainda não viraram texto, e apaga os temas vazios.
-- * organizar_midia: o áudio ou vídeo que está na fila de transcrição muda de tema (vai para o certo antes de virar
--   texto), ou volta para a fila ("Tentar novamente" do áudio que não abriu).
-- * limpar_tema: um tema sem nenhum arquivo e sem nada na fila deixa de existir. O áudio que não abriu (erro no arquivo)
--   continua anotado na lista "Não foi possível abrir", com "Tentar novamente".
-- Pode rodar mais de uma vez. Precisa do v34.
create or replace function organizar_midia(p_id text, p_acao text, p_para uuid default null) returns void
language plpgsql security definer set search_path = public as $$
declare de uuid; t_de uuid; t_para uuid; st text;
begin
  select x.materia_id, m.turma_id, x.status into de, t_de, st from midias x join materias m on m.id = x.materia_id where x.id::text = p_id;
  if de is null then raise exception 'Áudio ou vídeo não encontrado.'; end if;
  if not (eh_admin() or t_de = any(minhas_turmas())) then raise exception 'Sem permissão para mudar este áudio.'; end if;
  if p_acao = 'repetir' then
    update midias set status = 'fila', tentativas = 0, erro = null, atualizado_em = now() where id::text = p_id and status in ('erro', 'fila');
    return;
  end if;
  if p_acao <> 'mover' then raise exception 'Ação desconhecida.'; end if;
  -- (o que está sendo transcrito agora termina no tema de antes; a próxima análise muda o arquivo pronto)
  if st = 'processando' then raise exception 'Este áudio está sendo transcrito agora; tente de novo daqui a pouco.'; end if;
  select m.turma_id into t_para from materias m where m.id = p_para;
  if t_para is null or t_para <> t_de then raise exception 'Tema não encontrado.'; end if;
  if de = p_para then return; end if;
  update midias set materia_id = p_para where id::text = p_id;
  if not exists (select 1 from documentos where materia_id = de) and not exists (select 1 from midias where materia_id = de) then
    delete from materias where id = de;
  end if;
end $$;
revoke all on function organizar_midia(text, text, uuid) from public, anon;
grant execute on function organizar_midia(text, text, uuid) to authenticated;

create or replace function limpar_tema(p_mid uuid) returns boolean
language plpgsql security definer set search_path = public as $$
declare t uuid;
begin
  select turma_id into t from materias where id = p_mid;
  if t is null then return false; end if;
  if not (eh_admin() or t = any(minhas_turmas())) then raise exception 'Sem permissão para apagar este tema.'; end if;
  if exists (select 1 from documentos where materia_id = p_mid) or exists (select 1 from midias where materia_id = p_mid and status in ('fila', 'processando')) then return false; end if;
  -- o áudio ou vídeo que não abriu fica anotado (sem tema) e sai da fila; o que já virou texto não tem mais nada aqui
  insert into falhas_envio (materia_id, nome, drive_id, motivo, user_id)
    select null, x.nome, x.drive_id, 'Não foi possível abrir: erro no arquivo', auth.uid() from midias x where x.materia_id = p_mid and x.status = 'erro';
  delete from midias where materia_id = p_mid;
  update falhas_envio set materia_id = null where materia_id = p_mid;
  delete from materias where id = p_mid;
  return true;
end $$;
revoke all on function limpar_tema(uuid) from public, anon;
grant execute on function limpar_tema(uuid) to authenticated;
