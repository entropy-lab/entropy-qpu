from copy import deepcopy
from dataclasses import dataclass
from typing import Dict, List

from entropylab_qpudb._quaconfig import QuaConfig


@dataclass(frozen=True)
class Moment:
    play_statements: Dict[str, str]  # quantum element  # operation


class GateConcatenator:
    def __init__(self, moment_sequence: List[Moment], config: QuaConfig, name=None):
        # todo: add the ability to add more than one moment sequence
        self._moment_sequence = moment_sequence
        self._config = deepcopy(config)
        # collect all elements
        self._elements = set()
        for gate in moment_sequence:
            self._elements.update(gate.play_statements.keys())

        self._add_operations_to_config()
        self._add_empty_pulses_to_config()
        self._add_gates_to_config()

    def _add_operations_to_config(self):
        for element in self._elements:
            self._config["elements"][element]["operations"][
                "concat_waveform"
            ] = f"{element}_concat_pulse_in"

    def _add_empty_pulses_to_config(self):
        for element in self._elements:
            pulse_name = f"{element}_concat_pulse_in"
            self._config["pulses"][pulse_name] = {
                "length": 0,
                "operation": "control",
                "waveforms": {},
            }
            if "mixInputs" in self._config["elements"][element]:
                waveform_i_name = f"{element}_concat_waveform_i"
                waveform_q_name = f"{element}_concat_waveform_q"

                self._config["pulses"][pulse_name]["waveforms"] = {
                    "I": waveform_i_name,
                    "Q": waveform_q_name,
                }
                self._config["waveforms"][waveform_i_name] = {
                    "type": "arbitrary",
                    "samples": [],
                }
                self._config["waveforms"][waveform_q_name] = {
                    "type": "arbitrary",
                    "samples": [],
                }
            else:
                waveform_name = f"{element}_concat_waveform"
                self._config["pulses"][pulse_name]["waveforms"] = {
                    "single": waveform_name,
                }
                self._config["waveforms"][waveform_name] = {
                    "type": "arbitrary",
                    "samples": [],
                }

    def _add_gates_to_config(self):
        for moment in self._moment_sequence:
            duration = self._get_moment_duration(moment)
            for element in self._elements:
                concat_pulse = self._config["pulses"][f"{element}_concat_pulse_in"]
                concat_pulse["length"] += duration

                # add to concatenated waveforms the waveforms from this operation, add zeros to others
                if element in moment.play_statements.keys():
                    operation = moment.play_statements[element]
                    if "mixInputs" in self._config["elements"][element]:
                        waveform_i, waveform_q = self._config.get_waveforms_from_op(
                            element, operation
                        )
                        self._append_waveform(
                            f"{element}_concat_waveform_i", waveform_i, duration
                        )
                        self._append_waveform(
                            f"{element}_concat_waveform_q", waveform_q, duration
                        )
                    else:
                        waveform = self._config.get_waveforms_from_op(
                            element, operation
                        )
                        self._append_waveform(
                            f"{element}_concat_waveform", waveform, duration
                        )
                else:
                    if "mixInputs" in self._config["elements"][element]:
                        waveform_i = self._get_empty_waveform(duration)
                        waveform_q = self._get_empty_waveform(duration)
                        self._append_waveform(
                            f"{element}_concat_waveform_i", waveform_i, duration
                        )
                        self._append_waveform(
                            f"{element}_concat_waveform_q", waveform_q, duration
                        )
                    else:
                        waveform = self._get_empty_waveform(duration)
                        self._append_waveform(
                            f"{element}_concat_waveform", waveform, duration
                        )

    def _get_moment_duration(self, moment):
        duration = 0
        for element, operation in moment.play_statements.items():
            op_duration = self._config.get_pulse_from_op(element, operation)["length"]
            # op_duration = self._config['pulses'][self._config[element]['operations'][operation]]['length']
            duration = max(duration, op_duration)
        return duration

    def _append_waveform(self, name, waveform, duration):
        waveform_to_append = (
            waveform + [0.0] * (len(waveform) - duration)
            if duration > len(waveform)
            else waveform
        )
        self._config["waveforms"][name]["samples"] += waveform_to_append

    def _get_empty_waveform(self, duration):
        return [0.0] * duration

    @property
    def config(self):
        return self._config

    @staticmethod
    def concat_op_name():
        return "concat_waveform"

    @staticmethod
    def concat_pulse_name(element):
        return f"{element}_concat_pulse_in"

    def concat_waveform_name(self, element):
        if "mixInputs" in self._config["elements"][element]:
            return f"{element}_concat_waveform_i", f"{element}_concat_waveform_q"
        else:
            return f"{element}_concat_waveform"
