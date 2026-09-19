import pytest

from kicad2cad.sexp import SexpError, find, first, parse, value, xy


def test_nesting_and_atoms_stay_strings():
    tree = parse("(a (b 1 2.5) (c (d x)))")
    assert tree == ["a", ["b", "1", "2.5"], ["c", ["d", "x"]]]


def test_quoted_strings_keep_spaces_and_unescape():
    tree = parse(r'(t "hello world" "say \"honk\"" "a\\b")')
    assert tree[1:] == ["hello world", 'say "honk"', "a\\b"]


def test_empty_list_and_helpers():
    tree = parse('(n () (at 1 2) (at 3 4) (layer "F.Cu"))')
    assert tree[1] == []
    assert len(find(tree, "at")) == 2
    assert xy(first(tree, "at")) == (1.0, 2.0)
    assert value(tree, "layer") == "F.Cu"
    assert value(tree, "missing", "dflt") == "dflt"


@pytest.mark.parametrize("text", ["(a (b)", "(a))", "(a) (b)"])
def test_malformed_input_raises(text):
    with pytest.raises(SexpError):
        parse(text)
