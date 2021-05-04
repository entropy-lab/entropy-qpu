from entropylab_qpudb._gateconcatenator import GateConcatenator, Moment
from configuration import config, qpu_data, resolve


def test_gate_concatenator_alive():
    seq = [Moment({resolve.q(1, "z"): "flux", resolve.q(2, "z"): "flux"})]
    GateConcatenator(moment_sequence=seq, config=config)


def test_gate_concatenator_trivial_seq():
    seq = [Moment({resolve.q(1, "z"): "flux", resolve.q(2, "z"): "flux"})]
    gc = GateConcatenator(moment_sequence=seq, config=config)
    assert gc.concat_op_name() in gc.config["elements"][resolve.q(1, "z")]["operations"]
    assert gc.concat_pulse_name(resolve.q(1, "z")) in gc.config["pulses"]
    assert gc.concat_op_name() in gc.config["elements"][resolve.q(2, "z")]["operations"]
    assert gc.concat_pulse_name(resolve.q(2, "z")) in gc.config["pulses"]

    assert gc.config["waveforms"][gc.concat_waveform_name(resolve.q(1, "z"))][
        "samples"
    ] == gc.config.get_waveforms_from_op(resolve.q(1, "z"), "flux")
    assert gc.config["waveforms"][gc.concat_waveform_name(resolve.q(2, "z"))][
        "samples"
    ] == gc.config.get_waveforms_from_op(resolve.q(2, "z"), "flux")


def test_gate_concat_longer_sequence():
    seq1 = [
        Moment({resolve.q(1, "z"): "flux", resolve.q(2, "z"): "flux"}),
        Moment({resolve.q(1, "z"): "flux", resolve.q(2, "z"): "flux"}),
    ]

    gc1 = GateConcatenator(moment_sequence=seq1, config=config)

    flux_wf = gc1.config.get_waveforms_from_op(resolve.q(1, "z"), "flux")
    assert (
        gc1.config.get_waveforms_from_op(resolve.q(1, "z"), gc1.concat_op_name())
        == flux_wf + flux_wf
    )
    assert gc1.config.get_waveforms_from_op(
        resolve.q(2, "z"), gc1.concat_op_name()
    ) == gc1.config.get_waveforms_from_op(
        resolve.q(2, "z"), "flux"
    ) + gc1.config.get_waveforms_from_op(
        resolve.q(2, "z"), "flux"
    )

    seq2 = [
        Moment({resolve.q(1, "z"): "flux"}),
        Moment({resolve.q(2, "z"): "flux"}),
    ]

    gc2 = GateConcatenator(moment_sequence=seq2, config=config)
    assert (
        gc2.config.get_waveforms_from_op(resolve.q(2, "z"), gc2.concat_op_name())
        == [0.0] * len(flux_wf) + flux_wf
    )
    assert gc2.config.get_waveforms_from_op(
        resolve.q(1, "z"), gc2.concat_op_name()
    ) == flux_wf + [0.0] * len(flux_wf)
