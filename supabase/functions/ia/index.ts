// Função "ia" do Acervo da Turma (Supabase Edge Function, Deno).
// Recebe o pedido do app, confere se é membro da turma e repassa a uma das IAs gratuitas:
//   Gemini  (segredo GEMINI_API_KEY)  -> apostila, resumo e flashcards (textos longos)
//   Groq    (segredo GROQ_API_KEY)    -> metade dos pedaços da apostila, questões e tarefas curtas
//                                        (para as duas cotas grátis trabalharem juntas e a fila andar mais rápido)
//   Mistral (segredo MISTRAL_API_KEY) -> opcional; a chave de API do Mistral deixou de ser gratuita
// Se a IA preferida estiver sem cota, lenta ou sem chave, o pedido passa sozinho para a próxima.
// Só a do Gemini é obrigatória. Modelos opcionais: GEMINI_MODEL, MISTRAL_MODEL, GROQ_MODEL.
// Cada pedido fica anotado na tabela uso_ia (IA usada, tokens, limites), para o painel de cotas da Administração.
// Chave própria: um aluno pode mandar a chave grátis do Gemini da conta DELE (campo "chaves.gemini"); aí o Gemini
// daquele pedido usa a cota dele, não a da turma. A chave só é usada neste pedido: não é gravada nem anotada.
// Chave guardada: o aluno pode deixar o robô usar a chave dele (acao "guardar_chave"). Ela é gravada CIFRADA na tabela
// chaves_ia (ninguém lê pelo app) e só esta função a decifra, na hora de usar. O robô e o administrador usam todas as
// chaves guardadas como um time: cada pedido vai para a chave que está há mais tempo sem uso.
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
type Rastro = { falhas: string[]; dia: Set<Provedor>; groq?: { modelo: string; limite: number; restante: number }; propria?: boolean };
const POR_DIA = /per.?day|daily|\bRPD\b|\bTPD\b/i;

// Qual IA faz o quê (a primeira da lista é a preferida; as outras são reserva)
const ORDEM: Record<string, Provedor[]> = {
  apostila: ['gemini', 'groq', 'mistral'],
  resumo: ['gemini', 'mistral', 'groq'],
  flashcards: ['mistral', 'gemini', 'groq'],
  questoes: ['mistral', 'groq', 'gemini'],
  curta: ['groq', 'gemini', 'mistral'],
};
// Parte dos pedaços da apostila que vai primeiro para o Groq (o resto vai primeiro para o Gemini). Segredo opcional
// GROQ_PARTE_APOSTILA, de 0 a 1 (0 = o Groq só entra quando o Gemini não puder).
const PARTE_GROQ = Math.min(1, Math.max(0, Number(Deno.env.get('GROQ_PARTE_APOSTILA') ?? 0.5)));
const CHAVE: Record<Provedor, string> = { gemini: 'GEMINI_API_KEY', mistral: 'MISTRAL_API_KEY', groq: 'GROQ_API_KEY' };
const NOME: Record<Provedor, string> = { gemini: 'Gemini', mistral: 'Mistral', groq: 'Groq' };
// IA que pediu calma por muito tempo: pula até a hora indicada (vale enquanto esta cópia da função estiver ligada)
const descansoAte: Partial<Record<Provedor, number>> = {};
const esperaPedida = (r: Response) => Number(r.headers.get('retry-after') || 0) * 1000;

/* ---------- Gemini ----------
   Modelos escolhidos sozinhos entre os "Flash" estáveis disponíveis para a chave, do mais novo para o mais antigo.
   Os "Lite" ficam de reserva. Modelos que o Google recusar ("não disponível") são pulados nas próximas chamadas.
   Cada chave tem a sua lista (a chave da turma e as chaves próprias dos alunos podem ter acesso a modelos diferentes);
   as listas ficam guardadas pelo "resumo" (hash) da chave, nunca pela chave em si. */
const disponiveisPor = new Map<string, string[]>();
const recusadosPor = new Map<string, Set<string>>();
async function idChave(key: string) {
  const h = new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(key)));
  return Array.from(h.slice(0, 12), b => b.toString(16).padStart(2, '0')).join('');
}
function recusadosDe(id: string) {
  let r = recusadosPor.get(id);
  if (!r) { if (recusadosPor.size > 300) recusadosPor.clear(); r = new Set(); recusadosPor.set(id, r); }
  return r;
}
async function listarModelos(key: string, id: string) {
  const guardada = disponiveisPor.get(id); if (guardada) return guardada;
  const r = await fetch('https://generativelanguage.googleapis.com/v1beta/models?pageSize=200', { headers: { 'x-goog-api-key': key } });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error('Gemini recusou a chave: ' + (j.error?.message || r.status));
  const lista = (j.models || [])
    .filter((m: { supportedGenerationMethods?: string[] }) => (m.supportedGenerationMethods || []).includes('generateContent'))
    .map((m: { name: string }) => m.name.replace(/^models\//, ''));
  if (disponiveisPor.size > 300) disponiveisPor.clear();
  disponiveisPor.set(id, lista);
  return lista;
}
const versao = (n: string) => parseFloat((n.match(/^gemini-(\d+(?:\.\d+)?)/) || [])[1] || '0');
function ordenar(lista: string[], reserva: boolean, recusados: Set<string>) {
  const estaveis = lista.filter(n => /^gemini-\d+(\.\d+)?-flash(-lite)?$/.test(n) && !recusados.has(n));
  const flash = estaveis.filter(n => !n.endsWith('-lite')).sort((a, b) => versao(b) - versao(a));
  const lite = estaveis.filter(n => n.endsWith('-lite')).sort((a, b) => versao(b) - versao(a));
  return reserva ? [...lite, ...flash] : [...flash, ...lite];
}
/* Com o "pensamento" livre, os modelos Flash pensavam tanto nos pedidos grandes (questões, apostila) que passavam do
   limite de tempo da função (erro 504). Aqui o pensamento fica curto; o que se pede ao modelo não muda.
   Modelo que não aceitar o ajuste é chamado de novo sem ele. */
const semAjuste = new Set<string>();
function pensamento(modelo: string) {
  if (semAjuste.has(modelo)) return null;
  const v = versao(modelo);
  if (v >= 3) return { thinkingLevel: 'low' };
  if (v >= 2.5) return { thinkingBudget: modelo.endsWith('-lite') ? 0 : 1024 };
  return null;
}
async function chamarGemini(key: string, p: Pedido, prazo: number, rastro: Rastro): Promise<Ok | Falha> {
  const falhas = rastro.falhas;
  let lista: string[]; const id = await idChave(key); const recusados = recusadosDe(id);
  try { lista = await listarModelos(key, id); } catch (e) { return { ok: false, status: 401, msg: (e as Error).message, chave: true }; }
  const fixo = Deno.env.get('GEMINI_MODEL');
  const candidatos = [...new Set([...(fixo && lista.includes(fixo) ? [fixo] : []), ...ordenar(lista, p.reserva, recusados)])];
  if (!candidatos.length) return { ok: false, status: 500, msg: 'Nenhum modelo Gemini Flash disponível para esta chave.' };
  const body: Record<string, unknown> = {
    contents: [{ role: 'user', parts: [{ text: p.prompt }] }],
    generationConfig: { temperature: p.temperatura, maxOutputTokens: p.maxTokens, responseMimeType: p.formato === 'json' ? 'application/json' : 'text/plain' },
  };
  if (p.sistema) body.systemInstruction = { parts: [{ text: p.sistema }] };
  let ultima: Falha = { ok: false, status: 503, msg: 'Os modelos do Gemini estão sobrecarregados agora.' };
  const modelos = candidatos.slice(0, 8);
  for (let i = 0; i < modelos.length; i++) {
    const modelo = modelos[i];
    if (prazo - Date.now() < 15_000) break;
    const pensar = pensamento(modelo);
    const corpo = pensar ? { ...body, generationConfig: { ...(body.generationConfig as Record<string, unknown>), thinkingConfig: pensar } } : body;
    let r: Response;
    try {
      r = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${modelo}:generateContent`, {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'x-goog-api-key': key }, body: JSON.stringify(corpo),
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
    if (r.status === 400 && pensar && /think/i.test(msg)) { semAjuste.add(modelo); modelos.splice(i + 1, 0, modelo); continue; }   // não aceitou o ajuste: de novo sem ele
    if (r.status === 404 || /no longer available|not found|not supported|deprecated/i.test(msg)) { recusados.add(modelo); continue; }
    if (r.status === 401 || r.status === 403 || /API key not valid|API_KEY_INVALID|API key expired|ACCESS_TOKEN_TYPE_UNSUPPORTED/i.test(msg)) return { ok: false, status: 401, msg: msg || 'Chave do Gemini recusada.', chave: true };
    if (r.status === 429) {
      // cota do dia acabou neste modelo: os pedidos seguintes vão direto para a outra IA por uma hora
      if (POR_DIA.test(msg + JSON.stringify(j.error?.details || ''))) { if (!rastro.propria) descansoAte.gemini = Date.now() + 3_600_000; rastro.dia.add('gemini'); }
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
  // apostila e questões: pedidos maiores; primeiro o modelo com mais folga por minuto no plano gratuito
  'groq:apostila': ['meta-llama/llama-4-scout-17b-16e-instruct', 'llama-3.3-70b-versatile', 'openai/gpt-oss-120b'],
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
      if (maxSaida < Math.min(2000, p.maxTokens)) {
        falhas.push(`${prov}/${modelo}: texto grande demais`);
        if (!ultima.cota) ultima = { ok: false, status: 413, msg: `Texto grande demais para o ${NOME[prov]}.` }; continue;
      }
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
    if (r.ok && j.choices?.[0]?.finish_reason === 'length') { falhas.push(`${prov}/${modelo}: resposta cortada`); continue; }
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
    let r = await admin.from('uso_ia').insert(row);
    // banco sem o SQL v12 (sem a coluna do tema) ou sem o v8 (sem quem pediu): anota sem elas
    if (r.error && /materia_id/.test(r.error.message)) { const { materia_id, ...resto } = row; row = resto; r = await admin.from('uso_ia').insert(row); }
    if (r.error && /user_id|chave_id/.test(r.error.message)) { const { user_id, chave_id, ...resto } = row; await admin.from('uso_ia').insert(resto); }
    if (Math.random() < 0.005) await admin.from('uso_ia').delete().lt('em', new Date(Date.now() - 90 * 86_400_000).toISOString());
  } catch (_) { /* sem a tabela, só não anota */ }
}

/* ---------- Chaves guardadas dos alunos ----------
   Cifra AES-GCM com uma chave tirada do segredo de serviço do próprio Supabase: o texto gravado no banco não serve para
   nada sem ele (nem pelo SQL Editor). Se esse segredo for trocado, as chaves guardadas param e os alunos guardam de novo. */
async function chaveCifra() {
  const raw = new TextEncoder().encode('chaves-ia:' + (Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') || ''));
  return crypto.subtle.importKey('raw', await crypto.subtle.digest('SHA-256', raw), 'AES-GCM', false, ['encrypt', 'decrypt']);
}
async function cifrar(t: string) {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const c = new Uint8Array(await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, await chaveCifra(), new TextEncoder().encode(t)));
  const tudo = new Uint8Array(12 + c.length); tudo.set(iv); tudo.set(c, 12);
  return btoa(String.fromCharCode(...tudo));
}
async function decifrar(b64: string) {
  const tudo = Uint8Array.from(atob(b64), ch => ch.charCodeAt(0));
  return new TextDecoder().decode(await crypto.subtle.decrypt({ name: 'AES-GCM', iv: tudo.slice(0, 12) }, await chaveCifra(), tudo.slice(12)));
}
// meia-noite na Califórnia: quando a cota diária do Gemini recarrega
function proxMeiaNoitePT() {
  const agora = Date.now();
  const f = new Intl.DateTimeFormat('en-US', { timeZone: 'America/Los_Angeles', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' });
  const p = Object.fromEntries(f.formatToParts(new Date(agora)).map(x => [x.type, x.value]));
  const passou = ((+p.hour * 60 + +p.minute) * 60 + +p.second) * 1000;
  return new Date(agora - passou + 86_400_000 + 60_000).toISOString();
}
const FORMATO_CHAVE = /^(AIza[0-9A-Za-z_\-]{30,60}|AQ\.[0-9A-Za-z_\-.]{20,400})$/;
type Anotar = (ok: boolean, status: number, prov: Provedor, modelo: string | null, uso: unknown, extra?: Record<string, unknown>) => Promise<void>;
/* Tenta o pedido com as chaves guardadas (até 4 chaves). Chave sem cota descansa (2 minutos, ou até a cota do dia voltar);
   chave recusada pelo Google sai do time. Devolve a resposta pronta, ou null para seguir com a chave da turma. */
async function comChavesGuardadas(p: Pedido, prazo: number, falhas: string[], anotar: Anotar): Promise<Response | null> {
  if (!admin) return null;
  const evitar: string[] = [];
  for (let i = 0; i < 4 && prazo - Date.now() > 20_000; i++) {
    const { data, error } = await admin.rpc('pegar_chave_guardada', { evitar });
    const k = Array.isArray(data) ? data[0] : null;
    if (error || !k) return null;                     // sem chaves guardadas livres (ou sem o SQL v12)
    evitar.push(k.user_id);
    let key: string;
    try { key = await decifrar(k.cifrada); } catch { await admin.from('chaves_ia').update({ recusada_em: new Date().toISOString() }).eq('user_id', k.user_id); continue; }
    const rastro: Rastro = { falhas, dia: new Set(), propria: true };
    const r = await chamarGemini(key, p, prazo, rastro);
    const dono = { origem: 'chave-guardada', user_id: k.user_id, chave_id: k.chave_id, dia_gemini: rastro.dia.has('gemini') };
    if (r.ok) {
      await anotar(true, 200, 'gemini', r.modelo, r.uso, dono);
      return json({ texto: r.texto, modelo: r.modelo, provedor: 'gemini', guardada: true, fim: r.fim, uso: r.uso, tentativas: falhas });
    }
    await anotar(false, r.chave ? 502 : r.cota ? 429 : r.status, 'gemini', null, null, dono);
    if (r.chave) await admin.from('chaves_ia').update({ recusada_em: new Date().toISOString() }).eq('user_id', k.user_id);
    else if (r.cota) await admin.from('chaves_ia').update({ descanso_ate: rastro.dia.has('gemini') ? proxMeiaNoitePT() : new Date(Date.now() + 120_000).toISOString() }).eq('user_id', k.user_id);
    if (r.lento) return null;
  }
  return null;
}

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: cors });
  try {
    const sb = createClient(Deno.env.get('SUPABASE_URL')!, Deno.env.get('SUPABASE_ANON_KEY')!, {
      global: { headers: { Authorization: req.headers.get('Authorization') ?? '' } },
    });
    const { data: membro, error } = await sb.rpc('eh_membro');
    if (error || !membro) return json({ error: 'Só membros da turma podem usar a IA.' }, 403);

    const { prompt, sistema, formato = 'json', temperatura = 0.2, maxTokens = 24000, reserva = false, tarefa = 'apostila', provedor, evitar = [], origem = 'app', chaves, soPropria = false,
            acao, chave: chaveNova, materia_id = null, usarGuardadas = false } = await req.json();
    // chaves do Gemini: as antigas começam com "AIza"; as novas (de 2026 em diante) começam com "AQ."
    const propria = typeof chaves?.gemini === 'string' && FORMATO_CHAVE.test(chaves.gemini.trim()) ? chaves.gemini.trim() : null;
    if (soPropria && !propria) return json({ error: 'Chave própria do Gemini ausente ou em formato inválido.', propria: true, chave: true }, 400);
    // quem pediu (para cada aluno ver o próprio uso) e um resumo curto da chave própria (nunca a chave)
    let usuario: string | null = null, emailUsuario = '';
    try { const jwt = JSON.parse(atob((req.headers.get('Authorization') || '').replace(/^Bearer\s+/i, '').split('.')[1].replace(/-/g, '+').replace(/_/g, '/'))); usuario = jwt?.sub ?? null; emailUsuario = String(jwt?.email || '').toLowerCase(); } catch (_) { /* sem usuário */ }

    // guardar ou remover a chave que o aluno deixa o robô usar
    if (acao === 'guardar_chave' || acao === 'remover_chave') {
      if (!admin || !usuario) return json({ error: 'O servidor não está pronto para guardar chaves.' }, 500);
      if (acao === 'remover_chave') { await admin.from('chaves_ia').delete().eq('user_id', usuario); return json({ ok: true }); }
      const k = String(chaveNova || '').trim();
      if (!FORMATO_CHAVE.test(k)) return json({ error: 'Chave do Gemini em formato inválido.', chave: true }, 400);
      try { await listarModelos(k, await idChave(k)); } catch (e) { return json({ error: 'O Google recusou esta chave: ' + (e as Error).message, chave: true }, 400); }
      const { error: eg } = await admin.from('chaves_ia').upsert({ user_id: usuario, cifrada: await cifrar(k), final: k.slice(-4), chave_id: (await idChave(k)).slice(0, 10),
        ativa: true, recusada_em: null, descanso_ate: null, criado_em: new Date().toISOString() });
      if (eg) return json({ error: /chaves_ia/.test(eg.message) ? 'Falta rodar no Supabase o SQL v12.' : eg.message }, 500);
      return json({ ok: true, final: k.slice(-4) });
    }
    // o time de chaves guardadas trabalha só para a fila da turma: o robô e o administrador
    let podeGuardadas = false;
    if (usarGuardadas && !propria && admin) {
      podeGuardadas = emailUsuario === (Deno.env.get('ROBO_EMAIL') || 'robo-ia@example.com').toLowerCase();
      if (!podeGuardadas) { const { data } = await sb.rpc('eh_admin'); podeGuardadas = !!data; }
    }
    const chaveId = propria ? (await idChave(propria)).slice(0, 10) : null;
    const chaveDe = (x: Provedor) => (x === 'gemini' && propria) ? propria : Deno.env.get(CHAVE[x]);
    if (!prompt || typeof prompt !== 'string') return json({ error: 'Pedido vazio.' }, 400);
    if (prompt.length > 400_000) return json({ error: 'Texto grande demais para um pedido só.' }, 413);
    const p: Pedido = { prompt, sistema, formato, temperatura, maxTokens, reserva };

    // "provedor" testa uma IA só (botão "Testar a IA" do administrador); "evitar" pula as que já demoraram neste pedido
    let base = ORDEM[tarefa] || ORDEM.apostila;
    if (tarefa === 'apostila' && Math.random() < PARTE_GROQ) base = ['groq', ...base.filter(x => x !== 'groq')];   // divide a apostila entre as duas IAs
    if (propria) base = soPropria ? ['gemini'] : ['gemini', ...base.filter(x => x !== 'gemini')];   // com chave própria, o Gemini dela vem primeiro
    const ordem: Provedor[] = provedor ? [provedor] : base.filter(x => !(evitar as string[]).includes(x));
    const comChave = ordem.filter(x => chaveDe(x));
    if (!comChave.length) {
      const falta = provedor ? CHAVE[provedor as Provedor] : 'GEMINI_API_KEY';
      return json({ error: `Falta configurar a chave ${falta} nos segredos do Supabase.`, semChave: true }, provedor ? 424 : 500);
    }
    // as que estão descansando vão para o fim da fila, a que volta primeiro na frente (ainda podem salvar o pedido)
    const agora = Date.now();
    const descansa = (x: Provedor) => !(x === 'gemini' && propria) && descansoAte[x]! > agora;   // o descanso é da chave da turma
    const fila = [...comChave.filter(x => !descansa(x)),
      ...comChave.filter(x => descansa(x)).sort((a, b) => descansoAte[a]! - descansoAte[b]!)];

    const prazo = Date.now() + 125_000;                        // respeita o limite de tempo da função
    const rastro: Rastro = { falhas: [], dia: new Set(), propria: !!propria }; const falhas = rastro.falhas; const motivos: Falha[] = [];
    const inicio = Date.now(); let ultimo: Provedor = fila[0]; let propriaRecusada = false;
    const anotar: Anotar = (ok, status, prov, modelo, uso, extra = {}) => anotarUso({
      provedor: prov, modelo, tarefa: provedor ? 'teste' : String(tarefa).slice(0, 20), origem: prov === 'gemini' && propria ? 'chave-propria' : origem === 'robo' ? 'robo' : 'app', ok, status,
      tentativas: falhas.length + (ok ? 1 : 0), ms: Date.now() - inicio, ...tokensDe(prov, uso),
      dia_gemini: rastro.dia.has('gemini'), dia_groq: rastro.dia.has('groq'),
      groq_modelo: rastro.groq?.modelo ?? null, groq_limite: rastro.groq?.limite ?? null, groq_restante: rastro.groq?.restante ?? null,
      user_id: usuario, chave_id: prov === 'gemini' && propria ? chaveId : null, materia_id: typeof materia_id === 'string' ? materia_id : null, ...extra });
    for (const prov of fila) {
      if (prazo - Date.now() < 15_000) break;
      ultimo = prov;
      if (prov === 'gemini' && podeGuardadas) {           // primeiro o time de chaves guardadas dos alunos
        const g = await comChavesGuardadas(p, prazo, falhas, anotar); if (g) return g;
        if (prazo - Date.now() < 15_000) break;
      }
      const key = chaveDe(prov)!;
      const r = prov === 'gemini' ? await chamarGemini(key, p, prazo, rastro) : await chamarChat(prov, key, p, prazo, rastro, tarefa);
      if (r.ok) { await anotar(true, 200, prov, r.modelo, r.uso); return json({ texto: r.texto, modelo: r.modelo, provedor: prov, fim: r.fim, uso: r.uso, tentativas: falhas, ...(propriaRecusada ? { propriaRecusada } : {}) }); }
      if (prov === 'gemini' && propria && r.chave) propriaRecusada = true;
      motivos.push(r);
      if (r.cota && !descansoAte[prov] && !(prov === 'gemini' && propria)) descansoAte[prov] = Date.now() + 60_000;
      if (r.lento) { await anotar(false, 504, prov, null, null); return json({ error: r.msg, lento: prov, tentativas: falhas }, 504); }   // o app repete o pedido sem esta IA
    }
    // a chave própria foi recusada ou está sem cota: o app avisa a pessoa (e, fora da ajuda à fila, tenta de novo com a da turma)
    const falhouPropria = !!propria && ultimo === 'gemini' && fila.length === 1;
    if (motivos.length === 1 && motivos[0].chave) { await anotar(false, 502, ultimo, null, null); return json({ error: falhouPropria ? 'A sua chave do Gemini foi recusada. Confira se copiou a chave inteira.' : motivos[0].msg, propria: falhouPropria, chave: true, tentativas: falhas }, 502); }
    // "texto grande demais" para uma IA não conta: se as outras estão sem cota, o pedido é de cota (o robô faz pausa)
    const cota = motivos.some(m => m.cota) && motivos.every(m => m.cota || m.chave || m.status === 413);
    await anotar(false, cota ? 429 : 503, ultimo, null, null);
    const nomes = fila.map(x => NOME[x]).join(' e ');
    return json({
      error: cota ? `Limite gratuito atingido por agora (${nomes}).` : (motivos.at(-1)?.msg || 'As IAs estão sobrecarregadas agora.'),
      cota, propria: falhouPropria || (!!propria && motivos[0]?.cota && fila[0] === 'gemini'), tentativas: falhas,
    }, cota ? 429 : 503);
  } catch (e) {
    return json({ error: (e as Error).message }, 500);
  }
});
