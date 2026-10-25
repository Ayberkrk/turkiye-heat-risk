"""Population adapter call contract shared by the city validators.

The pipeline calls adapter functions positionally, so the validators compare
positional parameter counts rather than names (see the adapter contract in
CONTRIBUTING.md).
"""

from __future__ import annotations

import inspect

# Gerçek çağrı yerlerindeki (hvi.py) pozisyonel argüman sayısı - isim değil
# sayı karşılaştırılıyor, çünkü adapter yazarları parametrelere farklı isim
# verebilir (bkz. CONTRIBUTING.md'deki adapter sözleşmesi).
#   adapter.fetch_population_data(config)
#   adapter.build_neighborhood_layer(pbf_path, population_paths, config)
REQUIRED_ADAPTER_PARAM_COUNTS = {
    "fetch_population_data": 1,
    "build_neighborhood_layer": 3,
}
OPTIONAL_ADAPTER_PARAM_COUNTS = {
    "refresh_population_data": 1,
    "load_cached_population_data": 1,
}


def signature_param_count_error(fn, fn_name: str, expected: int) -> str | None:
    """`fn`'in pozisyonel parametre sayısının `expected` ile eşleştiğini
    doğrular; eşleşmezse hata metnini, uyuyorsa None döner.

    Zorunlu keyword-only parametre kabul edilmez; pipeline bunları geçmez.
    Zorunlu keyword-only parametresi olmayan `*args` imzası geçerli sayılır.
    """
    if not callable(fn):
        return f"Adapter alanı '{fn_name}' çağrılabilir değil"

    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return None  # imzası incelenemeyen bir çağrılabilir - sessizce atla

    params = list(sig.parameters.values())
    required_keyword_only = [
        p.name for p in params
        if p.kind is inspect.Parameter.KEYWORD_ONLY and p.default is inspect.Parameter.empty
    ]
    if required_keyword_only:
        names = ", ".join(required_keyword_only)
        return (
            f"Adapter fonksiyonu '{fn_name}' gerçek çağrıda yalnızca pozisyonel argümanlarla "
            f"kullanılıyor ama zorunlu keyword-only parametreleri var: {names}"
        )
    if any(p.kind is inspect.Parameter.VAR_POSITIONAL for p in params):
        return None

    positional = [
        p for p in params
        if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    required = [p for p in positional if p.default is inspect.Parameter.empty]

    if len(required) > expected or len(positional) < expected:
        return (
            f"Adapter fonksiyonu '{fn_name}' {expected} pozisyonel argümanla çağrılıyor "
            f"ama imzası {len(positional)} parametre kabul ediyor "
            f"({len(required)} tanesi zorunlu)"
        )
    return None
