import pytest
from gh_repo_exporter import has_doi, is_valid_doi 

# --- Fake GitHub objects ---

class FakeContentFile:
    def __init__(self, text):
        self.decoded_content = text.encode("utf-8")


class FakeRepo:
    def __init__(self, citation_text):
        self.citation_text = citation_text

    def get_contents(self, path):
        if path != "CITATION.cff":
            raise FileNotFoundError()
        return FakeContentFile(self.citation_text)

# --- Tests ---

def test_top_level_doi():
    # Valid Zenodo DOI in top-level doi field
    citation = """
    title: KABR Tools
    version: 3.0.0
    doi: "10.5281/zenodo.11288083"
    """
    repo = FakeRepo(citation)
    assert is_valid_doi("10.5281/zenodo.11288083") is True
    assert has_doi(repo) == "Yes"

def test_empty_doi_returns_no():
    # Empty DOI should be invalid
    assert is_valid_doi("") is False

def test_doi_with_spaces_returns_yes():
    # Leading/trailing spaces should be stripped
    assert is_valid_doi(" 10.5281/zenodo.1234567 ") is True
    
def test_identifiers_type_doi():
    citation = """
    title: Test
    identifiers:
      - type: doi
        value: "10.9999/zenodo.1234567"
    """
    repo = FakeRepo(citation)
    assert is_valid_doi("10.9999/zenodo.1234567") is True
    assert has_doi(repo) == "Yes"

def test_identifiers_doi():
    # Valid Zenodo DOI inside identifiers list
    citation = """
    title: Test
    identifiers:
      - doi: "10.9999/zenodo.10000000"
    """
    repo = FakeRepo(citation)
    assert is_valid_doi("10.9999/zenodo.10000000") is True
    assert has_doi(repo) == "Yes"   
    
def test_arxiv_doi_returns_no():
    # arXiv DOI is not a repo DOI
    citation = """
    title: Test
    identifiers:
      - type: doi
        value: "10.48550/arXiv.1234.5678"
    """
    repo = FakeRepo(citation)
    assert is_valid_doi("10.48550/arXiv.1234.5678") is False
    assert has_doi(repo) == "No"

def test_gibberish_doi_returns_no():
    # Random text should fail DOI validation
    citation = """
    title: Test
    doi: "AasdjfuaawSHUW"
    """
    repo = FakeRepo(citation)
    assert is_valid_doi("AasdjfuaawSHUW") is False
    assert has_doi(repo) == "No"

def test_references_dont_count():
    # DOI in references section should not count
    citation = """
    title: Test
    references:
      - doi: "11.1111/not-valid"
    """
    repo = FakeRepo(citation)
    assert has_doi(repo) == "No"

def test_no_doi():
    # CITATION file exists but has no DOI
    citation = """
    title: Test
    version: 1.0.0
    """
    repo = FakeRepo(citation)
    assert is_valid_doi(None) is False
    assert has_doi(repo) == "No"

def test_missing_citation_file():
    # Missing CITATION.cff should return No
    class NoCitationRepo:
        def get_contents(self, path):
            raise FileNotFoundError()

    repo = NoCitationRepo()
    assert has_doi(repo) == "No"