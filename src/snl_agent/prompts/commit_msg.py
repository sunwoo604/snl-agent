"""Prompt for turning a staged git diff into a conventional-commits message."""

from . import clip

SYSTEM = (
    "You write git commit messages in the Conventional Commits format. "
    "You reply with the commit message and nothing else: no preamble, no "
    "explanation, no markdown fences, no surrounding quotes."
)

_RULES = """\
Rules:
- Subject line: type(scope): summary
- type is one of: feat, fix, docs, style, refactor, perf, test, build, ci, chore, revert
- scope is optional; use the module or area touched, lowercase, no spaces
- summary is imperative mood, lowercase, no trailing period, at most 72 characters total
- Describe WHY/WHAT changed, not the mechanics of the diff
- Add a body only if the change genuinely needs explaining: blank line, then wrapped prose
"""

_EXAMPLES = """\
### Example 1
Diff:
diff --git a/src/api/auth.py b/src/api/auth.py
@@ -12,6 +12,9 @@ def login(user, password):
-    if user.password == password:
+    if bcrypt.checkpw(password.encode(), user.password_hash):
         return issue_token(user)
+    log.warning("failed login for %s", user.id)
     return None

Message:
fix(auth): verify passwords with bcrypt instead of plaintext

### Example 2
Diff:
diff --git a/README.md b/README.md
@@ -1,3 +1,11 @@
 # widgets
+
+## Installation
+
+    pip install widgets
+

Message:
docs(readme): add installation section

### Example 3
Diff:
diff --git a/src/cache.py b/src/cache.py
new file mode 100644
@@ -0,0 +1,24 @@
+class LRUCache:
+    def __init__(self, maxsize=128):
+        ...
diff --git a/tests/test_cache.py b/tests/test_cache.py
new file mode 100644
@@ -0,0 +1,15 @@
+def test_evicts_oldest():
+    ...

Message:
feat(cache): add LRU cache with size-bounded eviction
"""


def build(diff: str, feedback: str | None = None) -> str:
    """Assemble the user prompt for a staged diff."""
    parts = [
        _RULES,
        _EXAMPLES,
        "### Now your turn\nDiff:\n" + clip(diff),
    ]
    if feedback:
        parts.append(
            "Your previous answer was rejected: "
            f"{feedback}\nReturn only a corrected commit message."
        )
    parts.append("Message:")
    return "\n\n".join(parts)
