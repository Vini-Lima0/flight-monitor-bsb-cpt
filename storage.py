"""Leitura e escrita do histórico de preços e do estado de alertas já disparados."""

import csv
import json
import os
from datetime import date, datetime, timezone

HISTORY_PATH = os.path.join(os.path.dirname(__file__), "data", "history.csv")
ALERT_STATE_PATH = os.path.join(os.path.dirname(__file__), "data", "alert_state.json")

HISTORY_FIELDS = ["timestamp_utc", "data_ida", "data_volta", "preco", "moeda", "fonte"]


def append_history(preco: float, moeda: str, fonte: str, data_ida: str, data_volta: str) -> None:
    os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
    is_new = not os.path.exists(HISTORY_PATH)
    with open(HISTORY_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=HISTORY_FIELDS)
        if is_new:
            writer.writeheader()
        writer.writerow(
            {
                "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "data_ida": data_ida,
                "data_volta": data_volta,
                "preco": preco,
                "moeda": moeda,
                "fonte": fonte,
            }
        )


def lowest_historical_price(mes_alvo: str, duracao_dias: int) -> float | None:
    """Menor preço já registrado para o mesmo mês de viagem e duração.

    Com datas flexíveis, a combinação vencedora muda de uma execução para
    outra, então comparar por par de datas exato não faria sentido. O que
    é comparável é "a melhor passagem de N dias naquele mês".
    """
    if not os.path.exists(HISTORY_PATH):
        return None
    menor = None
    with open(HISTORY_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                ida = date.fromisoformat(row["data_ida"])
                volta = date.fromisoformat(row["data_volta"])
                preco = float(row["preco"])
            except (KeyError, ValueError):
                continue
            if ida.strftime("%Y-%m") != mes_alvo or (volta - ida).days != duracao_dias:
                continue
            if menor is None or preco < menor:
                menor = preco
    return menor


ALERT_STATE_DEFAULT = {
    "origem": None,
    "destino": None,
    "mes_alvo": None,
    "duracao_dias": None,
    "data_ida": None,
    "data_volta": None,
    "lowest_alerted_price": None,
}


def load_alert_state() -> dict:
    if not os.path.exists(ALERT_STATE_PATH):
        return dict(ALERT_STATE_DEFAULT)
    with open(ALERT_STATE_PATH, encoding="utf-8") as f:
        try:
            estado = json.load(f)
        except json.JSONDecodeError:
            return dict(ALERT_STATE_DEFAULT)
    return {**ALERT_STATE_DEFAULT, **estado}


def lowest_alerted_price_for(
    estado: dict, origem: str, destino: str, mes_alvo: str, duracao_dias: int
) -> float | None:
    """Preço já alertado, mas só se for para a MESMA viagem procurada.

    "Mesma viagem" aqui é rota + mês + duração, não um par de datas exato:
    com datas flexíveis a combinação vencedora muda entre execuções, e
    comparar por datas exatas faria o dedupe reiniciar toda hora. Trocar
    destino, mês ou duração no config.yaml zera o dedupe automaticamente.
    """
    mesma_viagem = (
        estado.get("origem") == origem
        and estado.get("destino") == destino
        and estado.get("mes_alvo") == mes_alvo
        and estado.get("duracao_dias") == duracao_dias
    )
    return estado.get("lowest_alerted_price") if mesma_viagem else None


def save_alert_state(state: dict) -> None:
    os.makedirs(os.path.dirname(ALERT_STATE_PATH), exist_ok=True)
    with open(ALERT_STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
