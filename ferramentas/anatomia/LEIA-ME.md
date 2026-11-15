# Anatomia 3D: como os modelos foram gerados

Os arquivos em `cloudflare/anatomia/` saem dos modelos do **BodyParts3D**
(© The Database Center for Life Science, licença CC BY 4.0,
https://dbarchive.biosciencedbc.jp/en/bodyparts3d/). Ao usar, mantenha o crédito que aparece na tela.

Para gerar de novo, baixe da pasta `LATEST` do site:

- `isa_BP3D_4.0_obj_99.zip` (os modelos), extraído numa pasta `bp3d/isa_BP3D_4.0_obj_99/`;
- `isa_inclusion_relation_list.txt` e `isa_element_parts.txt`, na pasta `bp3d/`.

Depois rode, nesta ordem (Python 3 com numpy):

1. `python3 isa_cls.py bp3d`: monta a árvore de cada peça (cria `isa_anc.json`).
2. `python3 cls.py bp3d`: separa as peças por sistema (cria `isa_anc2.json` e `sist.json`).
3. `python3 conv2.py bp3d ../../cloudflare/anatomia`: grava um `.bin.gz` por sistema.

`traduz.py` traduz os nomes do inglês para o português (por regras e dicionário). O índice da busca
(`nomes.json`) é feito a partir dos cabeçalhos dos `.bin.gz`.

Se os modelos mudarem, aumente `ANAT_V` no `index.html` para os aparelhos baixarem de novo.

## Formato do `.bin.gz`

`BP3D` + tamanho do cabeçalho (uint32) + cabeçalho JSON (peças: id, nome em inglês, nome em português,
vértices, triângulos) + posições (diferenças por eixo, em 1/8 mm, em planos de bytes) + índices
(código "maior até agora", 16 bits, em planos de bytes). Tudo em gzip.
