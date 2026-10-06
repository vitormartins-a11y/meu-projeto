// Função "ia" do Acervo da Turma (Supabase Edge Function, Deno).
// Recebe o pedido do app, confere se é membro da turma e repassa a uma das IAs gratuitas:
//   Gemini  (segredo GEMINI_API_KEY)  -> apostila, resumo e flashcards (textos longos)
//   Groq    (segredo GROQ_API_KEY)    -> questões e tarefas curtas (classificar arquivos, montar pastas de estudo)
//   Mistral (segredo MISTRAL_API_KEY) -> opcional; a chave de API do Mistral deixou de ser gratuita
// Se a IA preferida estiver sem cota, lenta ou sem chave, o pedido passa sozinho para a próxima.
// Só a do Gemini é obrigatória. Modelos opcionais: GEMINI_MODEL, MISTRAL_MODEL, GROQ_MODEL.
// Cada pedido fica anotado na tabela uso_ia (IA usada, tokens, limites), para o painel de cotas da Administração.
import { createClient } from 'jsr:@supabase/supabase-js@2';

const cors = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
};
const json = (o: unknown, status = 200) =>
  new Response(JSON.stringify(o), { status, headers: { ...cors, 'Content-Type': 'application/json' } });

type Provedor = 'gemini' | 'mistral' | 'groq';
type Pedido = { prompt: string; sistema?: string; formato: string; temperatura: number; maxTokens: number; reserva: boolean };
type Ok = { ok: true; texto: string; modelo: string; fim: string | null; uso: unknown };
type Falha = { ok: false; status: number; msg: string; cota?: boolean; lento?: boolean; chave?: boolean };
// O que aconteceu durante um pedido: tentativas que falharam, IAs que avisaram "acabou a cota do dia" e o que o Groq
// informou sobre o limite diário (o Gemini não informa quanto resta)
type Rastro = { falhas: string[]; dia: Set<Provedor>; groq?: { modelo: string; limite: number; restante: number } };
const POR_DIA = /per.?day|daily|\bRPD\b|\bTPD\b/i;

// Qual IA faz o quê (a primeira da lista é a preferida; as outras são reserva)
const ORDEM: Record<string, Provedor[]> = {
  apostila: ['gemini', 'mistral'],
  resumo: ['gemini', 'mistral'],
  flashcards: ['mistral', 'gemini'],
  questoes: ['mistral', 'groq', 'gemini'],
  curta: ['groq', 'gemini', 'mistral'],
};
const CHAVE: Record<Provedor, string> = { gemini: 'GEMINI_API_KEY', mistral: 'MISTRAL_API_KEY', groq: 'GROQ_API_KEY' };
const NOME: Record<Provedor, string> = { gemini: 'Gemini', mistral: 'Mistral', groq: 'Groq' };
// IA que pediu calma por muito tempo: pula até a hora indicada (vale enquanto esta cópia da função estiver ligada)
const descansoAte: Partial<Record<Provedor, number>> = {};
const esperaPedida = (r: Response) => Number(r.headers.get('retry-after') || 0) * 1000;

/* ---------- Gemini ----------
   Modelos escolhidos sozinhos entre os "Flash" estáveis disponíveis para a chave, do mais novo para o mais antigo.
   Os "Lite" ficam de reserva. Modelos que o Google recusar ("não disponível") são pulados nas próximas chamadas. */
let disponiveis: string[] | null = null;
const recusados = new Set<string>();
async function listarModelos(key: string) {
  if (disponiveis) return disponiveis;
  const r = await fetch('https://generativelanguage.googleapis.com/v1beta/models?pageSize=200', { headers: { 'x-goog-api-key': key } });
  const j = await r.json();
  if (!r.ok) throw new Error('Gemini recusou a chave: ' + (j.error?.message || r.status));
  disponiveis = (j.models || [])
    .filter((m: { supportedGenerationMethods?: string[] }) => (m.supportedGenerationMethods || []).includes('generateContent'))
    .map((m: { name: string }) => m.name.replace(/^models\//, ''));
  return disponiveis!;
}
const versao = (n: string) => parseFloat((n.match(/^gemini-(\d+(?:\.\d+)?)/) || [])[1] || '0');
function ordenar(lista: string[], reserva: boolean) {
  const estaveis = lista.filter(n => /^gemini-\d+(\.\d+)?-flash(-lite)?$/.test(n) && !recusados.has(n));
  const flash = estaveis.filter(n => !n.endsWith('-lite')).sort((a, b) => versao(b) - versao(a));
  const lite = estaveis.filter(n => n.endsWith('-lite')).sort((a, b) => versao(b) - versao(a));
  return reserva ? [...lite, ...flash] : [...flash, ...lite];
}
async function chamarGemini(key: string, p: Pedido, prazo: number, rastro: Rastro): Promise<Ok | Falha> {
  const falhas = rastro.falhas;
  let lista: string[];
  try { lista = await listarModelos(key); } catch (e) { return { ok: false, status: 401, msg: (e as Error).message, chave: true }; }
  const fixo = Deno.env.get('GEMINI_MODEL');
  const candidatos = [...new Set([...(fixo && lista.includes(fixo) ? [fixo] : []), ...ordenar(lista, p.reserva)])];
  if (!candidatos.length) return { ok: false, status: 500, msg: 'Nenhum modelo Gemini Flash disponível para esta chave.' };
  const body: Record<string, unknown> = {
    contents: [{ role: 'user', parts: [{ text: p.prompt }] }],
    generationConfig: { temperature: p.temperatura, maxOutputTokens: p.maxTokens, responseMimeType: p.formato === 'json' ? 'application/json' : 'text/plain' },
  };
  if (p.sistema) body.systemInstruction = { parts: [{ text: p.sistema }] };
  let ultima: Falha = { ok: false, status: 503, msg: 'Os modelos do Gemini estão sobrecarregados agora.' };
  for (const modelo of candidatos.slice(0, 8)) {
    if (prazo - Date.now() < 15_000) break;
    let r: Response;
    try {
      r = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${modelo}:generateContent`, {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'x-goog-api-key': key }, body: JSON.stringify(body),
        signal: AbortSignal.timeout(prazo - Date.now()),
      });
    } catch { falhas.push(`${modelo}: demorou demais`); return { ok: false, status: 504, msg: 'O Gemini demorou demais.', lento: true }; }
    const j = await r.json().catch(() => ({}));
    if (r.ok) {
      const cand = j.candidates?.[0];
      const texto = (cand?.content?.parts || []).filter((x: { thought?: boolean }) => !x.thought).map((x: { text?: string }) => x.text || '').join('');
      return { ok: true, texto, modelo, fim: cand?.finishReason || null, uso: j.usageMetadata || null };
    }
    falhas.push(`${modelo}: ${r.status}`);
    const msg = String(j.error?.message || '');
    if (r.status === 404 || /no longer available|not found|not supported|deprecated/i.test(msg)) { recusados.add(modelo); continue; }
    if (r.status === 401 || r.status === 403) return { ok: false, status: r.status, msg: msg || 'Chave do Gemini recusada.', chave: true };
    if (r.status === 429) {
      // cota do dia acabou neste modelo: os pedidos seguintes vão direto para a outra IA por uma hora
      if (POR_DIA.test(msg + JSON.stringify(j.error?.details || ''))) { descansoAte.gemini = Date.now() + 3_600_000; rastro.dia.add('gemini'); }
      ultima = { ok: false, status: 429, msg: 'Limite gratuito do Gemini atingido por agora.', cota: true }; continue;
    }
    if ([500, 503, 504].includes(r.status)) { if (!ultima.cota) ultima = { ok: false, status: 503, msg: msg || 'O Gemini está sobrecarregado agora.' }; continue; }
    return { ok: false, status: r.status, msg: msg || `Gemini respondeu ${r.status}` };
  }
  return ultima;
}

/* ---------- Mistral e Groq (mesmo formato de pedido, o de "chat") ---------- */
const MODELOS: Record<string, string[]> = {
  mistral: ['mistral-medium-latest', 'mistral-small-latest'],
  groq: ['llama-3.3-70b-versatile', 'openai/gpt-oss-120b', 'meta-llama/llama-4-scout-17b-16e-instruct', 'llama-3.1-8b-instant'],
  // questões: pedidos maiores; primeiro o modelo com mais folga por minuto no plano gratuito
  'groq:questoes': ['meta-llama/llama-4-scout-17b-16e-instruct', 'openai/gpt-oss-120b', 'llama-3.3-70b-versatile', 'moonshotai/kimi-k2-instruct'],
};
// Limites aproximados do plano gratuito do Groq: resposta máxima e tokens por minuto (pergunta + resposta).
// Se o Groq mudar os números, o pedido recusado só passa para o próximo modelo ou para outra IA.
const GROQ_LIMITE: Record<string, { saida: number; tpm: number }> = {
  'llama-3.3-70b-versatile': { saida: 32768, tpm: 12000 },
  'openai/gpt-oss-120b': { saida: 32768, tpm: 8000 },
  'meta-llama/llama-4-scout-17b-16e-instruct': { saida: 8192, tpm: 30000 },
  'moonshotai/kimi-k2-instruct': { saida: 16384, tpm: 10000 },
  'llama-3.1-8b-instant': { saida: 8192, tpm: 6000 },
};
const ENDERECO = { mistral: 'https://api.mistral.ai/v1/chat/completions', groq: 'https://api.groq.com/openai/v1/chat/completions' };
const LIMITE_SAIDA = { mistral: 32000, groq: 32000 };
const recusadosChat = new Set<string>();
async function chamarChat(prov: 'mistral' | 'groq', key: string, p: Pedido, prazo: number, rastro: Rastro, tarefa: string): Promise<Ok | Falha> {
  const falhas = rastro.falhas;
  const fixo = Deno.env.get(prov === 'mistral' ? 'MISTRAL_MODEL' : 'GROQ_MODEL');
  const candidatos = [...new Set([...(fixo ? [fixo] : []), ...(MODELOS[prov + ':' + tarefa] || MODELOS[prov])])].filter(m => !recusadosChat.has(prov + ':' + m));
  const entrada = Math.ceil(((p.sistema || '').length + p.prompt.length) / 3.2);   // tokens da pergunta, por estimativa
  let ultima: Falha = { ok: false, status: 503, msg: `O ${NOME[prov]} está sobrecarregado agora.` };
  for (const modelo of candidatos) {
    if (prazo - Date.now() < 15_000) break;
    let maxSaida = Math.min(p.maxTokens, LIMITE_SAIDA[prov]);
    const lim = prov === 'groq' ? GROQ_LIMITE[modelo] : undefined;
    if (lim) {
      maxSaida = Math.min(maxSaida, lim.saida, lim.tpm - entrada - 300);
      if (maxSaida < Math.min(2000, p.maxTokens)) { falhas.push(`${prov}/${modelo}: texto grande demais`); continue; }
    }
    const body: Record<string, unknown> = {
      model: modelo, temperature: p.temperatura, max_tokens: maxSaida,
      messages: [...(p.sistema ? [{ role: 'system', content: p.sistema }] : []), { role: 'user', content: p.prompt }],
    };
    if (p.formato === 'json') body.response_format = { type: 'json_object' };
    let r: Response;
    try {
      r = await fetch(ENDERECO[prov], {
        method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + key }, body: JSON.stringify(body),
        signal: AbortSignal.timeout(prazo - Date.now()),
      });
    } catch { falhas.push(`${prov}/${modelo}: demorou demais`); return { ok: false, status: 504, msg: `O ${NOME[prov]} demorou demais.`, lento: true }; }
    const j = await r.json().catch(() => ({}));
    const limDia = Number(r.headers.get('x-ratelimit-limit-requests')), restDia = Number(r.headers.get('x-ratelimit-remaining-requests'));
    if (prov === 'groq' && limDia > 0 && !isNaN(restDia)) rastro.groq = { modelo, limite: limDia, restante: restDia };
    if (r.ok && j.choices?.[0]?.finish_reason === 'length' && p.formato === 'json') { falhas.push(`${prov}/${modelo}: resposta cortada`); continue; }
    if (r.ok) {
      const c = j.choices?.[0]; const cont = c?.message?.content;
      const texto = Array.isArray(cont) ? cont.filter((x: { type?: string }) => x.type === 'text').map((x: { text?: string }) => x.text || '').join('') : String(cont || '');
      return { ok: true, texto, modelo: `${prov}/${modelo}`, fim: c?.finish_reason || null, uso: j.usage || null };
    }
    falhas.push(`${prov}/${modelo}: ${r.status}`);
    const msg = String(j.error?.message || j.message || j.detail || '');
    if (r.status === 401 || r.status === 403) return { ok: false, status: r.status, msg: msg || `Chave do ${NOME[prov]} recusada.`, chave: true };
    if (r.status === 404 || /model.*(not found|does not exist|decommissioned|invalid)|invalid model/i.test(msg)) { recusadosChat.add(prov + ':' + modelo); continue; }
    if (r.status === 429) {
      if (esperaPedida(r) > 60_000) descansoAte[prov] = Date.now() + esperaPedida(r);
      if (POR_DIA.test(msg)) rastro.dia.add(prov);
      ultima = { ok: false, status: 429, msg: `Limite gratuito do ${NOME[prov]} atingido por agora.`, cota: true }; continue;
    }
    if (r.status === 413) { if (!ultima.cota) ultima = { ok: false, status: 413, msg: `Texto grande demais para o ${NOME[prov]}.` }; continue; }
    if (r.status >= 500) { if (!ultima.cota) ultima = { ok: false, status: 503, msg: msg || `O ${NOME[prov]} está sobrecarregado agora.` }; continue; }
    // 400 (ex.: o modelo não conseguiu montar o JSON): tenta o próximo modelo
    ultima = { ok: false, status: r.status, msg: msg || `${NOME[prov]} respondeu ${r.status}` };
  }
  return ultima;
}

/* ---------- Registro de uso (painel de cotas) ----------
   Gravado com a chave de serviço do próprio Supabase (a turma não lê nem escreve nesta tabela; só o administrador lê).
   Se a tabela ainda não existir, o pedido segue normalmente. Registros com mais de 90 dias são apagados aos poucos. */
const admin = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') ? createClient(Deno.env.get('SUPABASE_URL')!, Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!) : null;
function tokensDe(prov: Provedor, uso: any) {
  if (!uso) return { tokens_in: null, tokens_out: null };
  if (prov === 'gemini') return { tokens_in: uso.promptTokenCount ?? null, tokens_out: (uso.candidatesTokenCount ?? 0) + (uso.thoughtsTokenCount ?? 0) };
  return { tokens_in: uso.prompt_tokens ?? null, tokens_out: uso.completion_tokens ?? null };
}
async function anotarUso(row: Record<string, unknown>) {
  if (!admin) return;
  try {
    await admin.from('uso_ia').insert(row);
    if (Math.random() < 0.005) await admin.from('uso_ia').delete().lt('em', new Date(Date.now() - 90 * 86_400_000).toISOString());
  } catch (_) { /* sem a tabela, só não anota */ }
}

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: cors });
  try {
    const sb = createClient(Deno.env.get('SUPABASE_URL')!, Deno.env.get('SUPABASE_ANON_KEY')!, {
      global: { headers: { Authorization: req.headers.get('Authorization') ?? '' } },
    });
    const { data: membro, error } = await sb.rpc('eh_membro');
    if (error || !membro) return json({ error: 'Só membros da turma podem usar a IA.' }, 403);

    const { prompt, sistema, formato = 'json', temperatura = 0.2, maxTokens = 24000, reserva = false, tarefa = 'apostila', provedor, evitar = [], origem = 'app' } = await req.json();
    if (!prompt || typeof prompt !== 'string') return json({ error: 'Pedido vazio.' }, 400);
    if (prompt.length > 400_000) return json({ error: 'Texto grande demais para um pedido só.' }, 413);
    const p: Pedido = { prompt, sistema, formato, temperatura, maxTokens, reserva };

    // "provedor" testa uma IA só (botão "Testar a IA" do administrador); "evitar" pula as que já demoraram neste pedido
    const ordem: Provedor[] = provedor ? [provedor] : (ORDEM[tarefa] || ORDEM.apostila).filter(x => !(evitar as string[]).includes(x));
    const comChave = ordem.filter(x => Deno.env.get(CHAVE[x]));
    if (!comChave.length) {
      const falta = provedor ? CHAVE[provedor as Provedor] : 'GEMINI_API_KEY';
      return json({ error: `Falta configurar a chave ${falta} nos segredos do Supabase.`, semChave: true }, provedor ? 424 : 500);
    }
    // as que estão descansando vão para o fim da fila, a que volta primeiro na frente (ainda podem salvar o pedido)
    const agora = Date.now();
    const fila = [...comChave.filter(x => !(descansoAte[x]! > agora)),
      ...comChave.filter(x => descansoAte[x]! > agora).sort((a, b) => descansoAte[a]! - descansoAte[b]!)];

    const prazo = Date.now() + 125_000;                        // respeita o limite de tempo da função
    const rastro: Rastro = { falhas: [], dia: new Set() }; const falhas = rastro.falhas; const motivos: Falha[] = [];
    const inicio = Date.now(); let ultimo: Provedor = fila[0];
    const anotar = (ok: boolean, status: number, prov: Provedor, modelo: string | null, uso: unknown) => anotarUso({
      provedor: prov, modelo, tarefa: provedor ? 'teste' : String(tarefa).slice(0, 20), origem: origem === 'robo' ? 'robo' : 'app', ok, status,
      tentativas: falhas.length + (ok ? 1 : 0), ms: Date.now() - inicio, ...tokensDe(prov, uso),
      dia_gemini: rastro.dia.has('gemini'), dia_groq: rastro.dia.has('groq'),
      groq_modelo: rastro.groq?.modelo ?? null, groq_limite: rastro.groq?.limite ?? null, groq_restante: rastro.groq?.restante ?? null });
    for (const prov of fila) {
      if (prazo - Date.now() < 15_000) break;
      ultimo = prov;
      const key = Deno.env.get(CHAVE[prov])!;
      const r = prov === 'gemini' ? await chamarGemini(key, p, prazo, rastro) : await chamarChat(prov, key, p, prazo, rastro, tarefa);
      if (r.ok) { await anotar(true, 200, prov, r.modelo, r.uso); return json({ texto: r.texto, modelo: r.modelo, provedor: prov, fim: r.fim, uso: r.uso, tentativas: falhas }); }
      motivos.push(r);
      if (r.cota && !descansoAte[prov]) descansoAte[prov] = Date.now() + 60_000;
      if (r.lento) { await anotar(false, 504, prov, null, null); return json({ error: r.msg, lento: prov, tentativas: falhas }, 504); }   // o app repete o pedido sem esta IA
    }
    if (motivos.length === 1 && motivos[0].chave) { await anotar(false, 502, ultimo, null, null); return json({ error: motivos[0].msg, tentativas: falhas }, 502); }
    const cota = motivos.length > 0 && motivos.every(m => m.cota || m.chave);
    await anotar(false, cota ? 429 : 503, ultimo, null, null);
    const nomes = fila.map(x => NOME[x]).join(' e ');
    return json({
      error: cota ? `Limite gratuito atingido por agora (${nomes}).` : (motivos.at(-1)?.msg || 'As IAs estão sobrecarregadas agora.'),
      cota, tentativas: falhas,
    }, cota ? 429 : 503);
  } catch (e) {
    return json({ error: (e as Error).message }, 500);
  }
});
