from enum import Enum


class MarketDirection(str, Enum):
    ALTA = "ALTA"
    BAIXA = "BAIXA"
    NEUTRA = "NEUTRA"
