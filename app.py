import os
import time
from flask import Flask, request
import requests

app = Flask(__name__)

# ====== Config (via variáveis de ambiente) ======
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN", "")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "minha-chave-de-verificacao")
PRIVACY_URL = os.getenv("PRIVACY_URL", "https://privacy.com.br/checkout/miasoph")

# Estado simples em memória (reinicia quando reinicia o servidor)
# status: "new" -> ainda não confirmou +18
#         "adult_ok" -> confirmou +18
# lang: idioma atual (pt/en/es) com base NA ÚLTIMA mensagem confiável
USER_STATE = {}


def send_text(psid: str, text: str) -> bool:
    """Envia uma mensagem de texto pelo Messenger."""
    if not PAGE_ACCESS_TOKEN:
        print("ERRO: PAGE_ACCESS_TOKEN não definido.")
        return False

    url = "https://graph.facebook.com/v19.0/me/messages"
    params = {"access_token": PAGE_ACCESS_TOKEN}
    payload = {"recipient": {"id": psid}, "message": {"text": text}}

    try:
        r = requests.post(url, params=params, json=payload, timeout=10)
        if r.status_code >= 400:
            print("Erro ao enviar:", r.status_code, r.text)
            return False
        return True
    except Exception as e:
        print("Exceção ao enviar:", e)
        return False


def normalize(text: str) -> str:
    return (text or "").strip().lower()


def detect_lang(text: str):
    """
    Heurística PT/EN/ES melhorada.
    Retorna: 'pt', 'en', 'es' ou None (quando não dá pra confiar).
    """
    t = normalize(text)
    if not t:
        return None

    # 1) Pedidos explícitos de idioma (troca imediata)
    # Exemplos: "do you speak english?", "I don't speak portuguese", "en español"
    if any(x in t for x in [
        "speak english", "do you speak english", "english please", "in english",
        "i dont speak portuguese", "i don't speak portuguese", "i dont speak portugués", "i don't speak portugués"
    ]):
        return "en"

    if any(x in t for x in [
        "fale português", "falar português", "em português",
        "speak portuguese", "in portuguese", "portuguese please", "português"
    ]):
        return "pt"

    if any(x in t for x in [
        "hablas español", "habla español", "en español", "español", "espanol", "hablas espanol"
    ]):
        return "es"

    # 2) Saudações curtas (agora troca mesmo com "hello"/"hi"/"hola"/"oi")
    short = t.replace("!", "").replace(".", "").replace("?", "").strip()
    if short in {"hi", "hello", "hey"}:
        return "en"
    if short in {"hola", "buenas"}:
        return "es"
    if short in {"oi", "olá", "ola"}:
        return "pt"

    # 3) Texto muito curto/ambíguo: não troca idioma
    if len(t) < 3:
        return None
    letters = sum(ch.isalpha() for ch in t)
    if letters < 2:
        return None

    # 4) Pontos por pistas (mais abrangente)
    pt_hints = [
        "você", "vc", "pra", "para", "com", "tudo bem", "preço", "preco", "quanto", "valor",
        "conteúdo", "conteudo", "quero", "sim", "não", "nao", "obrigad", "fotos", "vídeos", "videos",
        "privacidade", "seguro", "sigilo"
    ]
    en_hints = [
        "i ", "you", "do you", "can you", "what", "whats", "what's", "name", "price", "how much",
        "content", "link", "yes", "no", "thanks", "photo", "video", "speak", "dont", "don't",
        "privacy", "safe", "discreet"
    ]
    es_hints = [
        "yo", "tú", "tu", "puedes", "qué", "que", "como", "cuánto", "cuanto", "precio",
        "contenido", "quiero", "sí", "si", "gracias", "foto", "video", "hablas",
        "privacidad", "seguro", "discreto"
    ]

    pt_score = sum(1 for w in pt_hints if w in t)
    en_score = sum(1 for w in en_hints if w in t)
    es_score = sum(1 for w in es_hints if w in t)

    if pt_score == 0 and en_score == 0 and es_score == 0:
        return None

    if en_score > pt_score and en_score >= es_score:
        return "en"
    if es_score > pt_score and es_score > en_score:
        return "es"
    return "pt"


def tmsg(lang: str, key: str, privacy_url: str) -> str:
    """
    Pequeno dicionário de mensagens PT/EN/ES.
    """
    M = {
        "pt": {
            "greet_gate": "Oi, amor 💜 Eu sou a Mia.\nAntes de continuar: você confirma que é maior de 18 anos? (responda 'sim' ou 'não')",
            "need_18": "Antes de eu te atender melhor 💜 preciso confirmar: você é maior de 18 anos? (sim/não)",
            "adult_ok": f"Perfeito 💜 Obrigada por confirmar.\nAqui está o link do meu conteúdo exclusivo: {privacy_url}\nSe quiser, me diz o que você curte mais (mais soft, mais ousado, fotos, vídeos).",
            "adult_no": "Sem problemas 🙂 Por segurança, eu só posso continuar com maiores de 18.\nSe você mudar de ideia depois, pode voltar quando for +18.",
            "menu": "Opções:\n1) 'quero ver' (acesso)\n2) 'preço' (informações)\n3) 'privacidade' (como funciona)\n4) 'parar' (encerrar)\nDica: para receber o link, preciso confirmar que você é +18.",
            "stop": "Tudo bem 💜 Se quiser voltar, é só mandar 'oi'.",
            "privacy": f"Sim 💜 É tudo pelo Privacy, com acesso exclusivo e discreto.\nSe quiser o link de novo: {privacy_url}",
            "price": f"Lá no Privacy você vê os planos certinhos 💜\nQuer o link? {privacy_url}",
            "link": f"Aqui está 💜 {privacy_url}",
            "fallback": f"Entendi 💜 Me diz só uma coisa: você quer algo mais soft ou mais ousado?\nSe quiser o link direto: {privacy_url}",
        },
        "en": {
            "greet_gate": "Hi love 💜 I’m Mia.\nBefore we continue: can you confirm you’re 18+? (reply 'yes' or 'no')",
            "need_18": "Before I continue 💜 I need to confirm: are you 18+? (yes/no)",
            "adult_ok": f"Perfect 💜 Thanks for confirming.\nHere’s my exclusive content link: {privacy_url}\nTell me what you like more (soft, spicy, photos, videos).",
            "adult_no": "No worries 🙂 For safety, I can only continue with 18+.\nIf you come back later, please message me again when you’re 18+.",
            "menu": "Options:\n1) 'i want it' (access)\n2) 'price' (info)\n3) 'privacy' (how it works)\n4) 'stop' (end)\nTip: to get the link, I need you to confirm you’re 18+.",
            "stop": "All good 💜 If you want to come back, just say 'hi'.",
            "privacy": f"Yes 💜 It’s all on Privacy, exclusive and discreet.\nHere’s the link again: {privacy_url}",
            "price": f"You can see plans/pricing on Privacy 💜\nWant the link? {privacy_url}",
            "link": f"Here you go 💜 {privacy_url}",
            "fallback": f"Got it 💜 Tell me: do you prefer soft or spicy?\nDirect link: {privacy_url}",
        },
        "es": {
            "greet_gate": "Hola, amor 💜 Soy Mia.\nAntes de continuar: ¿puedes confirmar que eres mayor de 18? (responde 'sí' o 'no')",
            "need_18": "Antes de seguir 💜 necesito confirmar: ¿eres mayor de 18? (sí/no)",
            "adult_ok": f"Perfecto 💜 Gracias por confirmar.\nAquí está mi link de contenido exclusivo: {privacy_url}\nSi quieres, dime qué prefieres (más soft, más atrevido, fotos, videos).",
            "adult_no": "No hay problema 🙂 Por seguridad, solo puedo continuar con mayores de 18.\nSi vuelves después, escríbeme cuando seas +18.",
            "menu": "Opciones:\n1) 'quiero ver' (acceso)\n2) 'precio' (info)\n3) 'privacidad' (cómo funciona)\n4) 'parar' (terminar)\nTip: para enviarte el link, necesito confirmar que eres 18+.",
            "stop": "Listo 💜 Si quieres volver, solo di 'hola'.",
            "privacy": f"Sí 💜 Todo es por Privacy, exclusivo y discreto.\nAquí está el link otra vez: {privacy_url}",
            "price": f"En Privacy puedes ver los planes/precios 💜\n¿Quieres el link? {privacy_url}",
            "link": f"Aquí tienes 💜 {privacy_url}",
            "fallback": f"Entiendo 💜 Dime: ¿prefieres algo más soft o más atrevido?\nLink directo: {privacy_url}",
        },
    }
    base = M.get(lang, M["pt"])
    return base.get(key, M["pt"].get(key, ""))


def is_affirmative(text: str) -> bool:
    t = normalize(text)
    return t in {
        # PT
        "sim", "s", "claro", "ok", "confirmo", "sou", "tenho 18", "18+", "+18",
        # EN
        "yes", "y", "i'm 18", "im 18", "i am 18",
        # ES
        "sí", "si", "claro", "tengo 18", "soy mayor", "18+", "+18"
    }


def is_negative(text: str) -> bool:
    t = normalize(text)
    return t in {
        # PT
        "não", "nao", "n", "negativo",
        # EN/ES
        "no"
    }


def handle_message(psid: str, incoming_text: str):
    state = USER_STATE.get(psid, {"status": "new", "ts": time.time(), "lang": "pt"})
    status = state.get("status", "new")

    # ====== ALTERAÇÃO PRINCIPAL ======
    # idioma acompanha a ÚLTIMA mensagem recebida (se detecção for confiável)
    detected = detect_lang(incoming_text)
    if detected:
        state["lang"] = detected
    lang = state.get("lang", "pt")
    # ================================

    # Atualiza timestamp e persiste o estado sempre
    state["ts"] = time.time()
    USER_STATE[psid] = state

    t = normalize(incoming_text)

    # Comandos básicos
    if t in {"menu", "ajuda", "help"}:
        return send_text(psid, tmsg(lang, "menu", PRIVACY_URL))

    if t in {"parar", "stop", "cancelar"}:
        USER_STATE.pop(psid, None)
        return send_text(psid, tmsg(lang, "stop", PRIVACY_URL))

    # Se ainda não confirmou +18, gate
    if status != "adult_ok":
        if is_affirmative(t):
            USER_STATE[psid] = {"status": "adult_ok", "ts": time.time(), "lang": lang}
            return send_text(psid, tmsg(lang, "adult_ok", PRIVACY_URL))

        if is_negative(t):
            USER_STATE.pop(psid, None)
            return send_text(psid, tmsg(lang, "adult_no", PRIVACY_URL))

        # Mensagens comuns antes do gate
        if any(k in t for k in ["oi", "olá", "ola", "hey", "hello", "hi", "hola", "buenas"]):
            USER_STATE[psid] = {"status": "new", "ts": time.time(), "lang": lang}
            return send_text(psid, tmsg(lang, "greet_gate", PRIVACY_URL))

        if any(k in t for k in ["preço", "preco", "valor", "quanto", "price", "how much", "precio", "cuanto", "cuánto"]):
            USER_STATE[psid] = {"status": "new", "ts": time.time(), "lang": lang}
            return send_text(psid, tmsg(lang, "need_18", PRIVACY_URL))

        if any(k in t for k in ["link", "privacy", "conteúdo", "conteudo", "ver", "content", "see", "contenido", "enlace"]):
            USER_STATE[psid] = {"status": "new", "ts": time.time(), "lang": lang}
            return send_text(psid, tmsg(lang, "need_18", PRIVACY_URL))

        # fallback antes do gate
        USER_STATE[psid] = {"status": "new", "ts": time.time(), "lang": lang}
        return send_text(psid, tmsg(lang, "need_18", PRIVACY_URL))

    # Se já confirmou +18
    if any(k in t for k in ["link", "privacy", "conteúdo", "conteudo", "ver", "content", "see", "contenido", "enlace"]):
        return send_text(psid, tmsg(lang, "link", PRIVACY_URL))

    if any(k in t for k in ["preço", "preco", "valor", "quanto", "price", "how much", "precio", "cuanto", "cuánto"]):
        return send_text(psid, tmsg(lang, "price", PRIVACY_URL))

    if any(k in t for k in ["privacidade", "seguro", "sigilo", "privacy", "safe", "discreet", "privacidad", "discreto"]):
        return send_text(psid, tmsg(lang, "privacy", PRIVACY_URL))

    # fallback pós-gate
    return send_text(psid, tmsg(lang, "fallback", PRIVACY_URL))


# ====== Rotas do Webhook ======

@app.get("/webhook")
def verify_webhook():
    """
    Verificação do webhook:
    Meta envia hub.mode, hub.verify_token, hub.challenge
    """
    mode = request.args.get("hub.mode", "")
    token = request.args.get("hub.verify_token", "")
    challenge = request.args.get("hub.challenge", "")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge, 200
    return "Verification token mismatch", 403


@app.post("/webhook")
def handle_webhook_events():
    data = request.get_json(silent=True) or {}
    if data.get("object") != "page":
        return "Not a page event", 404

    for entry in data.get("entry", []):
        for messaging_event in entry.get("messaging", []):
            sender = (messaging_event.get("sender") or {}).get("id")
            if not sender:
                continue

            # Mensagens de texto
            message = messaging_event.get("message")
            if message and not message.get("is_echo"):
                text = message.get("text", "")
                handle_message(sender, text)

            # Postbacks (botões), se você usar depois
            postback = messaging_event.get("postback")
            if postback:
                payload = postback.get("payload", "")
                handle_message(sender, payload)

    return "EVENT_RECEIVED", 200


@app.get("/")
def health():
    return "OK", 200


if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)