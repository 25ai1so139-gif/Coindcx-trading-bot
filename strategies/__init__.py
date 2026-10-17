"""Register strategy classes here to expose them through the command line."""

from inspect import Parameter, signature

from strategies.momentum import Momentum
from strategies.sma_cross import SmaCross

STRATEGIES = {"sma_cross": SmaCross, "momentum": Momentum}


def create_strategy(name: str, **parameters):
    if name not in STRATEGIES:
        raise ValueError(f"unknown strategy: {name}")
    allowed = {key for key, value in signature(STRATEGIES[name]).parameters.items()
               if value.kind in {Parameter.POSITIONAL_OR_KEYWORD, Parameter.KEYWORD_ONLY}}
    supplied = {key: value for key, value in parameters.items() if value is not None}
    if supplied.keys() - allowed:
        raise ValueError(f"parameters do not apply to {name}: {', '.join(sorted(supplied.keys() - allowed))}")
    return STRATEGIES[name](**supplied)
