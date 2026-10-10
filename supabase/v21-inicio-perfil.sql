-- v21: início personalizável (widgets) e foto do perfil
-- * O jeito que cada pessoa arruma a tela Início (widgets, tamanhos, ordem) fica salvo na conta dela.
-- * Foto do perfil: aparece no chat e no canto da tela (pasta "avatares", pública; cada um só troca a própria).
-- * Fotos dos widgets (ex.: horário de aula): pasta "pessoal", só a própria pessoa vê.
-- Pode rodar mais de uma vez sem problema.

create table if not exists preferencias (
  user_id uuid primary key default auth.uid() references auth.users on delete cascade,
  inicio jsonb not null default '{}'::jsonb,
  atualizado_em timestamptz default now());
alter table preferencias enable row level security;
drop policy if exists minhas on preferencias;
create policy minhas on preferencias for all to authenticated using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

insert into storage.buckets (id, name, public) values ('avatares', 'avatares', true) on conflict (id) do nothing;
insert into storage.buckets (id, name, public) values ('pessoal', 'pessoal', false) on conflict (id) do nothing;
do $$ begin
  update storage.buckets set file_size_limit = 1048576, allowed_mime_types = array['image/jpeg', 'image/png', 'image/webp'] where id = 'avatares';
  update storage.buckets set file_size_limit = 3145728, allowed_mime_types = array['image/jpeg', 'image/png', 'image/webp'] where id = 'pessoal';
exception when undefined_column then null; end $$;

drop policy if exists "avatar enviar" on storage.objects;
create policy "avatar enviar" on storage.objects for insert to authenticated
  with check (bucket_id = 'avatares' and (storage.foldername(name))[1] = (select auth.uid())::text);
drop policy if exists "avatar trocar" on storage.objects;
create policy "avatar trocar" on storage.objects for update to authenticated
  using (bucket_id = 'avatares' and (storage.foldername(name))[1] = (select auth.uid())::text);
drop policy if exists "avatar apagar" on storage.objects;
create policy "avatar apagar" on storage.objects for delete to authenticated
  using (bucket_id = 'avatares' and (storage.foldername(name))[1] = (select auth.uid())::text);
drop policy if exists "pessoal dono" on storage.objects;
create policy "pessoal dono" on storage.objects for all to authenticated
  using (bucket_id = 'pessoal' and (storage.foldername(name))[1] = (select auth.uid())::text)
  with check (bucket_id = 'pessoal' and (storage.foldername(name))[1] = (select auth.uid())::text);

select 'Pronto: início personalizável e fotos.' as resultado;
