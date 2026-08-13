from repo_exporter.base import BaseExporter

# Simulate the API omitting zero-valued channels
api_response = {"red": 1}  # green/blue omitted because they're 0
literal = {"red": 1, "green": 0.5, "blue": 0.5}

print(BaseExporter._normalize_color(api_response))
print(BaseExporter._normalize_color(literal))
print(BaseExporter._normalize_color(api_response) == BaseExporter._normalize_color(literal))

same_full = {"red": 1, "green": 0.5, "blue": 0.5}
same_partial = {"red": 1, "green": 0.5, "blue": 0.5}
print(BaseExporter._normalize_color(same_full) == BaseExporter._normalize_color(same_partial))  # should be True