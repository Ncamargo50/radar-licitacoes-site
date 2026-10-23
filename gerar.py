"""Gera as paginas publicas "licitacoes abertas por UF e segmento" a partir da API publica do PNCP.

Roda todo dia no GitHub Actions (.github/workflows/paginas.yml). So biblioteca padrao do Python.
Saida: licitacoes/*.html, licitacoes/index.html, sitemap.xml e robots.txt.
"""

from __future__ import annotations

import json
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from html import escape
from pathlib import Path

BASE = "https://radar.pixadvisor.network"
PNCP = "https://pncp.gov.br/api/consulta/v1/contratacoes/proposta"
FORM = "https://docs.google.com/forms/d/e/1FAIpQLSeCdkLDeKVem-2vMUVAPgH8-Od4NkdKtuQl8WDfhzD0mvQ0XQ/viewform"
UFS = {"PR": "Paraná", "SP": "São Paulo", "SC": "Santa Catarina", "RS": "Rio Grande do Sul", "MG": "Minas Gerais",
       "RJ": "Rio de Janeiro", "GO": "Goiás", "DF": "Distrito Federal", "BA": "Bahia", "PE": "Pernambuco"}
PREP = {"PR": "no", "SP": "em", "SC": "em", "RS": "no", "MG": "em", "RJ": "no", "GO": "em", "DF": "no", "BA": "na",
        "PE": "em"}
MODALIDADES = [6, 8]  # pregao eletronico e dispensa: o grosso das compras de limpeza
SEGMENTOS = {
    "servicos-de-limpeza": {
        "titulo": "serviços de limpeza e conservação",
        "incluir": ["limpeza predial", "servicos de limpeza", "servico de limpeza", "conservacao predial", "asseio",
                    "zeladoria", "servente", "limpeza e conservacao"],
        "excluir": ["material de limpeza", "materiais de limpeza", "produtos de limpeza", "limpeza urbana", "fossa"],
    },
    "material-de-limpeza": {
        "titulo": "material de limpeza e higiene",
        "incluir": ["material de limpeza", "materiais de limpeza", "produtos de limpeza", "material de higiene",
                    "materiais de higiene", "saneantes", "higiene e limpeza", "limpeza e higiene"],
        "excluir": [],
    },
}
MAX_LISTA = 60


def norm(t: str | None) -> str:
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", t)


def casa(objeto: str, seg: dict) -> bool:
    o = norm(objeto)
    return not any(norm(x) in o for x in seg["excluir"]) and any(norm(x) in o for x in seg["incluir"])


def get_json(url: str):
    for espera in (2, 5, 15, 30):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "radar-licitacoes-paginas/1.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                corpo = r.read()
                return json.loads(corpo) if corpo else None
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            time.sleep(espera)
    return None


def abertas(uf: str, ate: date) -> list[dict]:
    itens = []
    for mod in MODALIDADES:
        pagina, total = 1, 1
        while pagina <= total and pagina <= 120:
            q = urllib.parse.urlencode({"dataFinal": ate.strftime("%Y%m%d"), "pagina": pagina, "tamanhoPagina": 50,
                                        "codigoModalidadeContratacao": mod, "uf": uf})
            d = get_json(f"{PNCP}?{q}") or {}
            total = int(d.get("totalPaginas") or 0)
            itens += d.get("data") or []
            pagina += 1
            time.sleep(0.3)
    return itens


def brl(v) -> str:
    return "sigiloso" if v is None else "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def data_br(iso: str | None) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%d/%m/%Y %H:%M")
    except (TypeError, ValueError):
        return "—"


def link_pncp(c: dict) -> str:
    return (f"https://pncp.gov.br/app/editais/{c['orgaoEntidade']['cnpj']}/{c['anoCompra']}/"
            f"{c['sequencialCompra']}")


CSS = """
:root{--cor:#0F766E;--tinta:#111827;--suave:#4b5563;--fundo:#fff;--borda:#e5e7eb;--faixa:#f0fdfa}
@media (prefers-color-scheme:dark){:root{--tinta:#e5e7eb;--suave:#9ca3af;--fundo:#0b1215;--borda:#1f2d2c;--faixa:#10201f}}
*{box-sizing:border-box}body{margin:0;font-family:system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif;
color:var(--tinta);background:var(--fundo);line-height:1.5}.wrap{max-width:1000px;margin:0 auto;padding:0 16px}
header{background:var(--cor);color:#fff;padding:14px 0}header a{color:#fff;text-decoration:none;font-weight:800}
h1{font-size:clamp(24px,4vw,34px);margin:24px 0 8px}.nota{color:var(--suave);font-size:14px}
.cta{display:block;background:var(--faixa);border:1px solid var(--borda);border-radius:12px;padding:16px;margin:20px 0}
.botao{display:inline-block;background:var(--cor);color:#fff;font-weight:800;padding:10px 16px;border-radius:8px;
text-decoration:none}.item{border:1px solid var(--borda);border-radius:10px;padding:12px 14px;margin:0 0 10px}
.item .meta{font-size:13px;color:var(--suave)}.item a{color:var(--cor);font-weight:700}
ul.hub{columns:2;padding-left:18px}@media (max-width:600px){ul.hub{columns:1}}
footer{border-top:1px solid var(--borda);margin-top:32px;padding:20px 0 40px;color:var(--suave);font-size:13px}
"""


def pagina(titulo: str, descricao: str, canonical: str, corpo: str) -> str:
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{escape(titulo)}</title>
<meta name="description" content="{escape(descricao)}"><link rel="canonical" href="{canonical}">
<style>{CSS}</style></head><body>
<header><div class="wrap"><a href="{BASE}/">Radar de Licitações</a></div></header>
<main class="wrap">{corpo}</main>
<footer><div class="wrap">Dados públicos do PNCP (Portal Nacional de Contratações Públicas), atualizados diariamente.
Confira sempre o edital original. <a href="{BASE}/licitacoes/">Todas as listas</a> ·
<a href="{BASE}/">Radar de Licitações</a></div></footer></body></html>"""


def cta(texto: str) -> str:
    return (f'<div class="cta"><b>{escape(texto)}</b><br><span class="nota">O Radar manda toda manhã, por e-mail, só '
            f'as licitações novas do seu ramo e estado, com resumo do edital por IA. 7 dias grátis, sem cartão.</span>'
            f'<br><br><a class="botao" href="{FORM}">Testar grátis</a></div>')


def main() -> None:
    hoje = date.today()
    ate = hoje + timedelta(days=45)
    agora = datetime.now(timezone(timedelta(hours=-3))).strftime("%d/%m/%Y %H:%M")
    saida = Path("licitacoes")
    saida.mkdir(exist_ok=True)
    urls, hub = [f"{BASE}/", f"{BASE}/licitacoes/"], []
    for uf, nome_uf in UFS.items():
        todas = abertas(uf, ate)
        for slug, seg in SEGMENTOS.items():
            itens = [c for c in todas if casa(c.get("objetoCompra"), seg)
                     and (c.get("dataEncerramentoProposta") or "") >= hoje.isoformat()]
            vistos, unicos = set(), []
            for c in sorted(itens, key=lambda c: c.get("dataEncerramentoProposta") or ""):
                if c.get("numeroControlePNCP") not in vistos:
                    vistos.add(c.get("numeroControlePNCP"))
                    unicos.append(c)
            arquivo = f"{slug}-{uf.lower()}.html"
            titulo = f"Licitações de {seg['titulo']} abertas {PREP[uf]} {nome_uf} ({len(unicos)}) — {hoje:%d/%m/%Y}"
            descricao = (f"{len(unicos)} licitações abertas de {seg['titulo']} {PREP[uf]} {nome_uf}, "
                         f"com valor, prazo e link do edital no PNCP. Atualizado em {hoje:%d/%m/%Y}.")
            lista = "".join(
                f'<div class="item"><div class="meta">{escape(c.get("modalidadeNome") or "")} · '
                f'{escape((c.get("unidadeOrgao") or {}).get("municipioNome") or "")}/{uf} · '
                f'propostas até {data_br(c.get("dataEncerramentoProposta"))}</div>'
                f'<div><b>{escape((c.get("objetoCompra") or "")[:240])}</b></div>'
                f'<div class="meta">{escape((c.get("orgaoEntidade") or {}).get("razaoSocial") or "")} · '
                f'valor estimado {brl(c.get("valorTotalEstimado"))}</div>'
                f'<a href="{link_pncp(c)}" rel="nofollow">Ver edital no PNCP →</a></div>'
                for c in unicos[:MAX_LISTA])
            corpo = (f"<h1>Licitações de {escape(seg['titulo'])} abertas {PREP[uf]} {escape(nome_uf)}</h1>"
                     f'<p class="nota">{len(unicos)} licitações com propostas abertas · atualizado em {agora}</p>'
                     + cta(f"Receba as novas licitações de {seg['titulo']} {PREP[uf]} {nome_uf} no seu e-mail")
                     + (lista or "<p>Nenhuma licitação aberta encontrada hoje.</p>")
                     + (f'<p class="nota">Mostrando as {MAX_LISTA} que encerram antes.</p>' if len(unicos) > MAX_LISTA else "")
                     + cta("Não perca a próxima"))
            (saida / arquivo).write_text(pagina(titulo, descricao, f"{BASE}/licitacoes/{arquivo}", corpo),
                                         encoding="utf-8")
            urls.append(f"{BASE}/licitacoes/{arquivo}")
            hub.append(f'<li><a href="{arquivo}">{escape(seg["titulo"].capitalize())} {PREP[uf]} {escape(nome_uf)}</a> '
                       f'({len(unicos)})</li>')
            print(uf, slug, len(unicos))
    (saida / "index.html").write_text(pagina(
        "Licitações de limpeza abertas por estado — Radar de Licitações",
        "Listas diárias de licitações abertas de serviços e material de limpeza por estado, com dados do PNCP.",
        f"{BASE}/licitacoes/",
        f"<h1>Licitações de limpeza abertas por estado</h1><p class='nota'>Atualizado em {agora}</p>"
        + cta("Receba só as novas do seu ramo, todo dia às 7h") + f'<ul class="hub">{"".join(hub)}</ul>'),
        encoding="utf-8")
    Path("sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"<url><loc>{u}</loc><lastmod>{hoje.isoformat()}</lastmod><changefreq>daily</changefreq></url>\n"
                  for u in urls) + "</urlset>\n", encoding="utf-8")
    Path("robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {BASE}/sitemap.xml\n", encoding="utf-8")


if __name__ == "__main__":
    main()
