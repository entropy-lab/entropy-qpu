# Entropy QPU DB

## Background
The entropy QPU DB is an extension designed to make it easy to calibrate
and manage experimentation of quantum processing units.
It provides two abilites:

1. to run automated calibrations of all parameters
related to the qubits, couplers and readout elements that make up a QPU,
using calibration graphs, as inspired by Google's [Optimus](https://arxiv.org/abs/1803.03226) method.

2. to store the calibration data in a persistent storage DB, and integrate that DB
into the calibration framework.
   
One of the challenges of bringing up a QPU from "scratch" is
that it's not always straightforward to understand which calibrations
need to be, at what order and with which parameters. On the other hand,
QPUs contain many parameters which require calibration and tracking,
which makes automated tools essential for this task.

This means that the process of building the calibration graph for a QPU needs to be
needs to be both flexible and powerful. The QPU DB is designed to allow to do just that.

## Getting started

This package requires having entropy installed, which can be obtained from pipy [here](https://pypi.org/project/entropylab/).

To get started, check out the tutorials under `docs/`.

## Contact info

The QPU DB was conceived and developed by [Lior Ella](https://github.com/liorella-qm),
[Gal Winer](https://github.com/galwiner), Ilan Mitnikov and Yonatan Cohen, and is
maintained by [Guy Kerem](https://github.com/qguyk). For any questions, suggestions or otherwise - please contact us on
our [discord server](https://discord.com/channels/806244683403100171/817087420058304532)!