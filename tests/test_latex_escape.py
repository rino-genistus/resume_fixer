from backend.pipeline.render import latex_escape


def test_hash():
    assert latex_escape("C#") == r"C\#"


def test_ampersand():
    assert latex_escape("R&D") == r"R\&D"


def test_percent():
    assert latex_escape("50%") == r"50\%"


def test_underscore():
    assert latex_escape("node_modules") == r"node\_modules"


def test_dollar():
    assert latex_escape("$100") == r"\$100"


def test_braces():
    assert latex_escape("{scope}") == r"\{scope\}"


def test_tilde_and_caret():
    assert latex_escape("~/bin ^top") == r"\textasciitilde{}/bin \textasciicircum{}top"


def test_backslash_not_double_escaped():
    assert latex_escape(r"C:\path") == r"C:\textbackslash{}path"


def test_no_special_chars_unchanged():
    assert latex_escape("PostgreSQL") == "PostgreSQL"


def test_multiple_special_chars_in_one_string():
    assert latex_escape("50% R&D on C# & C_2") == r"50\% R\&D on C\# \& C\_2"
