def calculate_score(
    trend: float = 0,
    pressure: float = 0,
    structure: float = 0,
    rejection: float = 0,
    volume: float = 0,
    confirmation: float = 0,
) -> float:
    """Calcula um score normalizado de 0 a 100.

    Pesos iniciais são apenas fundação técnica e deverão ser calibrados
    com testes/replay antes de qualquer uso operacional.
    """
    weights = {
        "trend": 0.20,
        "pressure": 0.20,
        "structure": 0.20,
        "rejection": 0.15,
        "volume": 0.10,
        "confirmation": 0.15,
    }
    values = {
        "trend": trend,
        "pressure": pressure,
        "structure": structure,
        "rejection": rejection,
        "volume": volume,
        "confirmation": confirmation,
    }
    score = sum(values[k] * weights[k] for k in weights)
    return max(0.0, min(100.0, score))
