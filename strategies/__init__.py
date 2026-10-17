"""Register strategy classes here to expose them through the command line."""

from strategies.momentum import Momentum
from strategies.sma_cross import SmaCross

STRATEGIES = {"sma_cross": SmaCross, "momentum": Momentum}
