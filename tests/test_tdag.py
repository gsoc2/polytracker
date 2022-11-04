import pytest
from polytracker import taint_dag, ProgramTrace, InputOutputMapping
from typing import cast
from pathlib import Path


@pytest.mark.program_trace("test_tdag.cpp")
def test_tdfile(program_trace: ProgramTrace):
    assert isinstance(program_trace, taint_dag.TDProgramTrace)

    tdfile = program_trace.tdfile
    assert tdfile.label_count == 14 # 8 source labels, 5 unions/ranges + zero-label (unused)

    t1 = cast(taint_dag.TDSourceNode, tdfile.decode_node(1))
    assert isinstance(t1, taint_dag.TDSourceNode)
    assert t1.affects_control_flow is True

    t2 = cast(taint_dag.TDSourceNode, tdfile.decode_node(2))
    assert isinstance(t2, taint_dag.TDSourceNode)
    assert t2.affects_control_flow is True

    t12 = cast(taint_dag.TDRangeNode, tdfile.decode_node(12))
    assert isinstance(t12, taint_dag.TDRangeNode)
    assert t12.first == 1
    assert t12.last == 4

    assert len(tdfile.fd_headers) == 2
    assert len(list(tdfile.sinks)) == 6


@pytest.mark.program_trace("test_tdag.cpp")
def test_td_taint_forest(program_trace: ProgramTrace):
    assert isinstance(program_trace, taint_dag.TDProgramTrace)

    tdfile = program_trace.tdfile
    # Basic properties
    tdforest = cast(taint_dag.TDTaintForest, program_trace.taint_forest)
    assert isinstance(tdforest, taint_dag.TDTaintForest)
    assert len(tdforest) == tdfile.label_count
    # Range node unfolding
    nodes = list(tdforest.nodes())
    assert len(nodes) - abs(tdforest.synth_label_cnt) + 1 == tdfile.label_count
    # Basic node properties
    n1 = tdforest.get_node(1)
    assert n1.parent_labels is None
    assert n1.source is not None
    assert n1.affected_control_flow is True

    n2 = tdforest.get_node(2)
    assert n2.parent_labels is None
    assert n2.source is not None
    assert n2.affected_control_flow is True

    n12 = tdforest.get_node(12)
    assert n12.parent_labels == (-2, 4)
    assert n12.source is None
    assert n12.affected_control_flow is False
    # Synthetic nodes
    assert tdforest.get_node(-1).parent_labels == (1, 2)
    assert tdforest.get_node(-2).parent_labels == (-1, 3)

@pytest.mark.program_trace("test_tdag.cpp")
def test_input_output_mapping(program_trace: ProgramTrace):
    assert isinstance(program_trace, taint_dag.TDProgramTrace)

    tdfile = program_trace.tdfile

    iomapping = InputOutputMapping(tdfile)
    m = iomapping.mapping()

    # There should be 6 inputs that make it to the output
    assert len(m) == 6

    # TODO (hbrodin): There has to be a better way of knowing the paths than hard coding.
    input_path = Path("/polytracker/tests/test_data/test_data.txt")
    output_path = Path("/polytracker/tests/test_data/test_data.txt.out")

    r2_outputs = {(output_path, 0), (output_path, 1), (output_path, 2), (output_path, 3)}
    eq_outputs = {(output_path, 4)}

    # Offset zero in input is present in output (via r2 and eq)
    assert (input_path, 0) in m.keys()
    assert m[(input_path, 0)] == r2_outputs.union(eq_outputs) 

    # Offsets 1,2,3 in input is present in output (via r2)
    assert (input_path, 1) in m.keys()
    assert m[(input_path, 1)] == r2_outputs
    assert (input_path, 2) in m.keys()
    assert m[(input_path, 2)] == r2_outputs
    assert (input_path, 3) in m.keys()
    assert m[(input_path, 3)] == r2_outputs

    # data[4] (from test_tdag.cpp) written to output
    assert (input_path, 4) in m.keys()
    assert m[(input_path, 4)] == {(output_path, 5)}

    # data[7] is in eq, written to output 4
    assert (input_path, 7) in m.keys()
    assert m[(input_path, 7)] == {(output_path, 4)}

@pytest.mark.program_trace("test_tdag.cpp")
def test_cavity_detection(program_trace: ProgramTrace):
    assert isinstance(program_trace, taint_dag.TDProgramTrace)

    tdfile = program_trace.tdfile

    iomapping = InputOutputMapping(tdfile)
    cav = iomapping.file_cavities()

    # TODO (hbrodin): There has to be a better way of knowing the paths than hard coding.
    input_path = Path("/polytracker/tests/test_data/test_data.txt")
    assert input_path in cav.keys()
    assert cav[input_path] == [(5, 6), (8, 29)]
