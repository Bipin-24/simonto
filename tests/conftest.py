import pytest

from simonto.graph import load_graph, load_model


@pytest.fixture(scope="session")
def graph():
    return load_graph()


@pytest.fixture(scope="session")
def model(graph):
    return load_model(graph)
