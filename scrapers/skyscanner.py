"""Scraper de fallback usando o Skyscanner, para quando o Google Flights
estiver instável demais para o scraping (layout mudou, bloqueio, timeout).

Mesma ressalva do google_flights.py: não é uma API oficial, pode quebrar.
"""

import logging
from datetime import datetime

from playwright.sync_api import sync_playwright

from scrapers.common import extract_prices

logger = logging.getLogger(__name__)

BASE_URL = "https://www.skyscanner.com.br/transporte/passagens-aereas"


def _yymmdd(data_iso: str) -> str:
    return datetime.strptime(data_iso, "%Y-%m-%d").strftime("%y%m%d")


def _build_url(origem: str, destino: str, data_ida: str, data_volta: str) -> str:
    return (
        f"{BASE_URL}/{origem.lower()}/{destino.lower()}/"
        f"{_yymmdd(data_ida)}/{_yymmdd(data_volta)}/"
    )


def buscar_menor_preco(origem: str, destino: str, data_ida: str, data_volta: str, moeda: str) -> float:
    """Retorna o menor preço encontrado na página de resultados do Skyscanner.

    Levanta RuntimeError se não conseguir extrair nenhum preço plausível.
    """
    url = _build_url(origem, destino, data_ida, data_volta)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        contexto = browser.new_context(locale="pt-BR")
        page = contexto.new_page()
        try:
            page.goto(url, timeout=45_000, wait_until="domcontentloaded")

            for texto_botao in ["Aceitar tudo", "Accept all cookies", "Aceitar"]:
                try:
                    botao = page.get_by_role("button", name=texto_botao)
                    if botao.is_visible(timeout=2_000):
                        botao.click()
                        break
                except Exception:
                    pass

            page.wait_for_timeout(10_000)
            try:
                page.wait_for_load_state("networkidle", timeout=25_000)
            except Exception:
                logger.warning("networkidle não atingido a tempo, seguindo com o texto atual da página")

            conteudo = page.inner_text("body")
        finally:
            browser.close()

    precos = extract_prices(conteudo, moeda)
    if not precos:
        raise RuntimeError("Nenhum preço encontrado na página do Skyscanner (layout pode ter mudado)")

    return min(precos)
