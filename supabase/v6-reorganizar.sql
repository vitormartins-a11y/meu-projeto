-- v6: o administrador pode reorganizar a biblioteca (mudar especialidade e área de um tema e juntar temas repetidos)
drop policy if exists admin_altera on materias;
create policy admin_altera on materias for update to authenticated using (eh_admin()) with check (eh_admin());
drop policy if exists admin_altera on documentos;
create policy admin_altera on documentos for update to authenticated using (eh_admin()) with check (eh_admin());
