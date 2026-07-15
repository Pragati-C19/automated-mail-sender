"""
parse_report.py
Reads accessibility-report.txt and returns a dict:
  { "https://www.example.com": ["Color contrast issues", "Missing image alt text", ...] }
Top 3-4 issues only, in plain English for non-technical readers.
"""

import re

# Maps axe rule IDs to plain English descriptions for non-tech readers
RULE_LABELS = {
    "color-contrast":               "Color contrast issues (text hard to read)",
    "image-alt":                    "Missing alternative text on images",
    "label":                        "Form fields missing labels",
    "link-name":                    "Links without descriptive text",
    "button-name":                  "Buttons without descriptive text",
    "html-has-lang":                "Missing page language declaration",
    "aria-input-field-name":        "ARIA input fields missing accessible names",
    "aria-required-children":       "ARIA roles missing required child elements",
    "landmark-banner-is-top-level": "Incorrect banner landmark structure",
    "landmark-no-duplicate-banner": "Duplicate banner landmarks",
    "landmark-unique":              "Non-unique landmark regions",
    "region":                       "Page content outside landmark regions",
    "list":                         "Incorrectly structured lists",
    "keyboard-navigation":          "Keyboard navigation issues",
    "skip-link":                    "Missing or inaccessible skip links",
}

# Priority order — show these first if present
PRIORITY_RULES = [
    "color-contrast",
    "image-alt",
    "label",
    "link-name",
    "button-name",
    "keyboard-navigation",
    "aria-input-field-name",
]


def parse_report(report_path: str) -> dict:
    """
    Returns dict mapping website URL -> list of plain-English issue strings (top 3-4).
    """
    with open(report_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    # Strip ANSI colour codes from axe output
    ansi_escape = re.compile(r'\x1b\[[0-9;]*m')
    content = ansi_escape.sub("", content)

    results = {}
    # Split into per-website blocks
    blocks = re.split(r'={40,}', content)

    current_url = None
    for block in blocks:
        block = block.strip()
        if not block:
            continue

        # Detect website header line
        url_match = re.search(r'Website:\s*(https?://\S+)', block)
        if url_match:
            current_url = url_match.group(1).strip()
            results[current_url] = []
            continue

        if current_url is None:
            continue

        # Extract all violated rule IDs from the block
        # axe prints: Violation of "rule-id" with N occurrences!
        violations = re.findall(r'Violation of "([^"]+)"', block)

        if not violations:
            continue

        # Sort by priority then alphabetically
        def sort_key(rule):
            try:
                return PRIORITY_RULES.index(rule)
            except ValueError:
                return len(PRIORITY_RULES)

        violations_sorted = sorted(set(violations), key=sort_key)

        # Convert to plain English, take top 4
        plain = []
        for rule in violations_sorted[:4]:
            label = RULE_LABELS.get(rule, rule.replace("-", " ").title())
            plain.append(label)

        # If more than 4 issues found, add an "etc." hint
        if len(set(violations)) > 4:
            plain.append("among other issues")

        results[current_url] = plain

    return results


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "data/dummy_accessibility_report.txt"
    data = parse_report(path)
    for url, issues in data.items():
        print(f"\n{url}")
        for i in issues:
            print(f"  - {i}")
