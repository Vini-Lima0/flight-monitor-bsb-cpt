"""Scraper do Google Flights via Playwright.

Google Flights não tem API pública. Isso aqui abre a página normal
(headless) e lê o texto renderizado procurando por valores monetários.
É frágil por natureza: se o Google mudar o layout, isso pode parar de
funcionar sem aviso — ver limitações no README.
"""

import logging
from urllib.parse import quote

from playwright.sync_api import sync_playwright

from scrapers.common import escolher_menor_preco, extract_prices

logger = logging.getLogger(__name__)

BASE_URL = "https://www.google.com/travel/flights"


def montar_url(origem: str, destino: str, data_ida: str, data_volta: str, moeda: str) -> str:
    """URL de busca do trajeto, já com rota e datas selecionadas.

    É a mesma URL que o scraper abre — serve também para ir junto no alerta,
    para você abrir direto o trajeto (não é link de pagamento/reserva).
    """
    texto = f"voos de {origem} para {destino} em {data_ida} voltando em {data_volta}"
    return f"{BASE_URL}?q={quote(texto)}&hl=pt-BR&curr={moeda}"


def buscar_menor_preco(origem: str, destino: str, data_ida: str, data_volta: str, moeda: str) -> float:
    """Retorna o menor preço encontrado na página de resultados do Google Flights.

    Levanta RuntimeError se não conseguir extrair nenhum preço plausível.
    """
    url = montar_url(origem, destino, data_ida, data_volta, moeda)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        contexto = browser.new_context(locale="pt-BR")
        page = contexto.new_page()
        try:
            page.goto(url, timeout=45_000, wait_until="domcontentloaded")

            # Fecha diálogo de consentimento de cookies do Google, se aparecer.
            for texto_botao in ["Aceitar tudo", "Accept all", "Concordo", "I agree"]:
                try:
                    botao = page.get_by_role("button", name=texto_botao)
                    if botao.is_visible(timeout=2_000):
                        botao.click()
                        break
                except Exception:
                    pass

            # Espera os resultados carregarem (a busca é feita via JS após o load).
            page.wait_for_timeout(8_000)
            try:
                page.wait_for_load_state("networkidle", timeout=20_000)
            except Exception:
                logger.warning("networkidle não atingido a tempo, seguindo com o texto atual da página")

            conteudo = page.inner_text("body")
        finally:
            browser.close()

    precos = extract_prices(conteudo, moeda)
    if not precos:
        raise RuntimeError("Nenhum preço encontrado na página do Google Flights (layout pode ter mudado)")

    preco, confiavel = escolher_menor_preco(precos)
    if not confiavel:
        logger.warning(
            "Preço %.2f aparece uma única vez na página (baixa confiança — "
            "pode ser ruído de banner/sugestão não relacionado à rota buscada)",
            preco,
        )
    return preco
