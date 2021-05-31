from abc import ABC, abstractmethod
from typing import Union


class Resolver(ABC):
    def __init__(self, aliases: Union[dict, None] = None):
        if aliases is None:
            self._aliases = {}
        else:
            self._aliases = aliases

    @abstractmethod
    def q(self, qubit, channel=None):
        pass

    @abstractmethod
    def res(self, resonator):
        pass

    @abstractmethod
    def coupler(self, qubit1, qubit2):
        pass

    @property
    def aliases(self):
        return self._aliases


class DefaultResolver(Resolver):
    def q(self, qubit, channel=None):
        if channel is None:
            return f"q{qubit}"
        else:
            return f"q{qubit}_{channel}"

    def res(self, resonator):
        return f"res{resonator}"

    def coupler(self, qubit1, qubit2):
        qubit1, qubit2 = sorted((qubit1, qubit2))
        return f"c{qubit1}_{qubit2}"
