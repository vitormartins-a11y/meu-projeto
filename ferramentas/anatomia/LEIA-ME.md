# Anatomia 3D: como os modelos foram gerados

Os arquivos em `cloudflare/anatomia/` saem do **Z-Anatomy** (https://www.z-anatomy.com, repositório
`Z-Anatomy/Models-of-human-anatomy`, licença CC BY-SA 4.0), que por sua vez é feito a partir do **BodyParts3D**
(© The Database Center for Life Science). Os arquivos convertidos também ficam sob CC BY-SA 4.0: mantenha o crédito
que aparece na tela.

Para gerar de novo (Python 3 com numpy, sem Blender):

1. Baixe o repositório do Z-Anatomy e extraia `Z-Anatomy.zip` (sai `Z-Anatomy/Startup.blend`, Blender 3.5).
2. `python3 zextrai.py Startup.blend itens.pkl`: lê o arquivo do Blender (`blend.py` é um leitor mínimo do formato)
   e grava malhas, curvas (nervos e vasos), rótulos e linhas indicadoras, já na posição do corpo.
3. `python3 z2site.py itens.pkl TA2.csv ../../cloudflare/anatomia`: separa por camada, dá as cores, faz os tubos dos
   nervos e vasos, traduz os nomes (TA2.csv, a Terminologia Anatômica que vem no repositório, coluna em português, e
   `traduz.py` quando falta) e grava:
   - um `.bin.gz` por camada;
   - `nomes.json` (a busca);
   - `acidentes.json` e `acidentes.bin.gz` (os acidentes de cada estrutura e as áreas de origem e inserção dos músculos).

Se os modelos mudarem, aumente `ANAT_V` no `index.html` para os aparelhos baixarem de novo.

## Formato do `.bin.gz`

`BP3D` + tamanho do cabeçalho (uint32) + cabeçalho JSON (peças: id, nome original, nome em português, cor, vértices,
triângulos) + posições (diferenças por eixo, em 1/8 mm, em planos de bytes) + índices (código "maior até agora",
16 bits, em planos de bytes). Tudo em gzip.
