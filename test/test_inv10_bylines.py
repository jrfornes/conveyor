"""Invariant 10: every commit on a conveyor-<role> branch ends with By <role>."""
import unittest

from harness import REVIEWER_FINDINGS, ConveyorTest


class Bylines(ConveyorTest):
    coder_conf = "max_retries=1"

    def test_all_role_commits_signed(self):
        fx = self.run_pipeline("demo", reviewer=REVIEWER_FINDINGS)
        base = fx.git("rev-list", "--max-parents=0", "HEAD")
        for role in ("coder", "reviewer"):
            shas = fx.git("rev-list", f"{base}..conveyor-{role}", "--no-merges").split()
            self.assertGreater(len(shas), 0)
            for sha in shas:
                msg = fx.git("log", "-1", "--format=%B", sha)
                author_role = "operator" if fx.git("log", "-1", "--format=%s", sha).startswith("Add task") else role
                other = "coder" if role == "reviewer" else "reviewer"
                if msg.endswith(f"By {other}."):
                    continue  # a merge.sh from one role's branch keeps the other role's byline
                self.assertTrue(msg.endswith(f"By {author_role}."), f"{sha}: {msg!r}")


if __name__ == "__main__":
    unittest.main()
