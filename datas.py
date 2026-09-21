"""Cálculo da data de busca real a partir da data alvo da viagem.

A maioria das companhias aéreas (e por consequência o Google Flights e o
Skyscanner) não deixa buscar/comprar passagens com mais de ~330 dias de
antecedência. Como a viagem alvo (`data_ida_alvo`/`data_volta_alvo`) pode
estar a mais de 12 meses de distância, este módulo decide, a cada execução,
qual data efetivamente buscar:

- Se a data alvo já está dentro do horizonte de busca, usa a data alvo direto.
- Senão, usa a data mais distante que dá pra buscar hoje (hoje + horizonte),
  mantendo a mesma duração de viagem (`data_volta_alvo - data_ida_alvo`).

Como o horizonte de busca "anda junto" com o calendário, a cada dia que passa
a data buscada se aproxima automaticamente da data alvo, até finalmente
coincidir com ela quando a viagem entrar no horizonte de antecedência máxima.
"""

from datetime import date, datetime, timedelta

HORIZONTE_PADRAO_DIAS = 330


def calcular_datas_busca(cfg: dict, hoje: date | None = None) -> tuple[str, str, bool]:
    """Retorna (data_ida, data_volta, e_data_alvo) a usar na busca de hoje.

    `e_data_alvo` indica se a data retornada é a data alvo real da viagem
    (True) ou uma data provisória, ajustada ao horizonte máximo de busca
    (False) — útil pra logar e pra decidir como comparar com o histórico.
    """
    hoje = hoje or date.today()
    alvo_ida = datetime.strptime(cfg["data_ida_alvo"], "%Y-%m-%d").date()
    alvo_volta = datetime.strptime(cfg["data_volta_alvo"], "%Y-%m-%d").date()
    duracao = (alvo_volta - alvo_ida).days
    horizonte = int(cfg.get("horizonte_max_dias", HORIZONTE_PADRAO_DIAS))

    limite_maximo = hoje + timedelta(days=horizonte)

    if alvo_ida <= limite_maximo:
        return alvo_ida.isoformat(), alvo_volta.isoformat(), True

    ida_provisoria = limite_maximo
    volta_provisoria = ida_provisoria + timedelta(days=duracao)
    return ida_provisoria.isoformat(), volta_provisoria.isoformat(), False
