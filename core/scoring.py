def calculate_score(
    trend: float = 0,
    pressure: float = 0,
    structure: float = 0,
    rejection: float = 0,
    volume: float = 0,
    confirmation: float = 0,
) -> float:
    """Calcula score técnico normalizado entre 0 e 100."""

    values = {
        "trend": trend,
        "pressure": pressure,
        "structure": structure,
        "rejection": rejection,
        "volume": volume,
        "confirmation": confirmation,
    }

    weights = {
        "trend": 0.20,
        "pressure": 0.20,
        "structure": 0.20,
        "rejection": 0.15,
        "volume": 0.10,
        "confirmation": 0.15,
    }

    for name, value in values.items():
        if not isinstance(value, (int, float)):
            raise ValueError(f"{name} deve ser numérico.")

    score = sum(values[name] * weights[name] for name in weights)

    return max(0.0, min(100.0, score))
