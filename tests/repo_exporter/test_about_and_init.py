def test_package_exports_and_version():
    import repo_exporter
    assert repo_exporter.__version__ == "2.0.0"
    assert repo_exporter.GitHubExporter is not None
    assert repo_exporter.HuggingFaceExporter is not None