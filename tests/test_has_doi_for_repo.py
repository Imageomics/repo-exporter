import pytest
from gh_repo_exporter import has_doi

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
    citation = """
    title: KABR Tools
    version: 3.0.0
    doi: "10.5281/zenodo.11288083"
    """
    repo = FakeRepo(citation)
    assert has_doi(repo) == "Yes"

def test_identifiers_type_doi():
    citation = """
    title: Test
    identifiers:
      - type: doi
        value: "10.9999/test"
    """
    repo = FakeRepo(citation)
    assert has_doi(repo) == "Yes"

def test_identifiers_doi():
    citation = """
    title: Test
    identifiers:
      - doi: "10.9999/zenodo.10000000"
    """
    repo = FakeRepo(citation)
    assert has_doi(repo) == "Yes"

def test_references_dont_count():
    citation = """
    title: Test
    references:
      - doi: "11.1111/not-valid"
    """
    repo = FakeRepo(citation)
    assert has_doi(repo) == "No"

def test_no_doi():
    citation = """
    title: Test
    version: 1.0.0
    """
    repo = FakeRepo(citation)
    assert has_doi(repo) == "No"

def test_missing_citation_file():
    class NoCitationRepo:
        def get_contents(self, path):
            raise FileNotFoundError()

    repo = NoCitationRepo()
    assert has_doi(repo) == "No"