"""uv run python -m esim.templates   prints the reference for every scene template."""

from esim.templates import TEMPLATES, reference

print(f"# Scene templates ({len(TEMPLATES)})\n")
print(reference())
