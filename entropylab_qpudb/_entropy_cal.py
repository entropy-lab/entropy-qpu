import enum
import inspect
from abc import abstractmethod
from copy import deepcopy
from dataclasses import dataclass
from itertools import count
from typing import Callable, List, Optional, Union, Iterable, Set

from entropylab_qpudb._quaconfig import QuaConfig
from entropylab.api.execution import EntropyContext
from entropylab.api.graph import Node
from entropylab.graph_experiment import PyNode


class AncestorRunStrategy(enum.Enum):
    RunAll = 1
    RunOnlyLast = 2


@dataclass
class ConfigPatch:
    id: int
    depth: int
    function: Callable

    def __hash__(self):
        return self.id


@dataclass
class QuaCalNodeOutput:
    base_config: QuaConfig
    patches: List[ConfigPatch]
    merged_config = None

    def build_config(self, context):
        config_copy = deepcopy(self.base_config)
        for patch in self.patches:
            patch.function(config_copy, context)
        self.merged_config = config_copy
        return config_copy

    def __repr__(self):
        merged = ""
        if self.merged_config:
            merged = str(self.merged_config)
        nl = "\n"
        return f"""
Base:
{self.base_config}

Patches:
{nl.join([(f"{patch.id} depth {patch.depth}:{nl}" + inspect.getsource(patch.function)) for patch in self.patches])}

Merged:
{merged}
"""


id_iter = count(start=0, step=1)


class QuaCalNode(PyNode):
    def __init__(
        self,
        dependency: Optional[Union[Node, Iterable[Node]]] = None,
        must_run_after: Set[Node] = None,
        name: Optional[str] = None,
    ):
        if dependency:
            if isinstance(dependency, Iterable):
                input_vars = {}
                for node in dependency:
                    input_vars[f"config_{node.label}_{id(node)}"] = node.outputs[
                        "config"
                    ]
            else:
                input_vars = {
                    f"config_{dependency.label}": dependency.outputs["config"]
                }
        else:
            input_vars = None
        output_vars = {"config"}

        def program(
            *configs,
            strategy: AncestorRunStrategy = AncestorRunStrategy.RunAll,
            is_last: bool,
            context: EntropyContext,
        ):
            # sync config
            merged_config: QuaCalNodeOutput = self._merge_configs(configs)
            config_copy = merged_config.build_config(context)

            # run the actual code
            self.prepare_config(config_copy, context)
            if strategy == AncestorRunStrategy.RunAll or is_last:
                self.run_program(config_copy, context)

            # prepare the output
            patch_depth = (
                max([config.depth for config in merged_config.patches] + [0]) + 1
            )
            merged_config.patches.append(
                ConfigPatch(next(id_iter), patch_depth, self.prepare_config)
            )
            merged_config.patches.append(
                ConfigPatch(next(id_iter), patch_depth, self.update_config)
            )
            return {"config": merged_config}

        if name is None:
            name = self.__class__.__name__
        super().__init__(name, program, input_vars, output_vars, must_run_after)

    def add_config_dependency(self, node):
        super().add_input(f"config_{node.label}", node.outputs["config"])

    def _merge_configs(self, configs: Iterable[QuaCalNodeOutput]) -> QuaCalNodeOutput:
        def get_base(config):
            if isinstance(config, QuaCalNodeOutput):
                return config.base_config
            else:
                return config

        def get_patches(config):
            if isinstance(config, QuaCalNodeOutput):
                return config.patches
            else:
                return []

        base_configs = [get_base(config) for config in configs]
        if len(set([id(config) for config in base_configs])) > 1:
            raise RuntimeError("trying to merge different configs")
        all_patches = [item for sublist in configs for item in get_patches(sublist)]
        unique_patches = list(set(all_patches))
        unique_patches.sort(key=lambda patch: patch.depth)
        return QuaCalNodeOutput(base_configs[0], unique_patches)

    @abstractmethod
    def prepare_config(self, config: QuaConfig, context: EntropyContext):
        pass

    @abstractmethod
    def run_program(self, config, context: EntropyContext):
        pass

    @abstractmethod
    def update_config(self, config: QuaConfig, context: EntropyContext):
        pass
