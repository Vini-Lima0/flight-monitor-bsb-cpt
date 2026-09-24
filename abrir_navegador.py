"""Abre um navegador visível com perfil persistente, para login manual.

Rode isto quando quiser que o bot passe a enxergar as opções de reserva de
agências (123milhas etc.), que o Google só mostra para sessões logadas.
Faça login no Google na janela que abrir e depois feche a janela: a sessão
fica salva em .browser-profile/ (nunca versionado) e as buscas seguintes a
reaproveitam.

    .venv/bin/python abrir_navegador.py [url]
"""

import os
import sys

from playwright.sync_api import sync_playwright

PERFIL = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".browser-profile")

URL_PADRAO = (
    "https://www.google.com/travel/flights/booking?tfs=CAIQAhpAEgoyMDI3LTA1LTAxIiAKA0JTQhIKMjAyNy0"
    "wNS0wMRoDU0RVKgJHMzIEMTgwMGoHCAESA0JTQnIHCAESA1NEVRpAEgoyMDI3LTA1LTA4IiAKA1NEVRIKMjAyNy0wNS0w"
    "OBoDQlNCKgJHMzIEMTgxM2oHCAESA1NEVXIHCAESA0JTQkABSAFwAYIBCwj___________8BmAEB"
    "&tfu=EgIgAg&hl=pt-BR&curr=BRL"
)


def main() -> int:
    url = sys.argv[1] if len(sys.argv) > 1 else URL_PADRAO
    os.makedirs(PERFIL, exist_ok=True)

    with sync_playwright() as p:
        contexto = p.chromium.launch_persistent_context(
            PERFIL,
            headless=False,
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
            viewport={"width": 1400, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = contexto.pages[0] if contexto.pages else contexto.new_page()
        page.goto(url, timeout=90_000, wait_until="domcontentloaded")

        print("Janela aberta. Faça login no Google se quiser que o bot veja as")
        print("opções de agências. Feche a janela quando terminar.")
        try:
            page.wait_for_event("close", timeout=0)
        except Exception:
            pass
        contexto.close()
    print("Sessão salva em .browser-profile/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
