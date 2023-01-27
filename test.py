import unittest, git, argparse
from manim import *

from git_sim.git_sim import GitSim


class TestGitSim(unittest.TestCase):
    def test_git_sim(self):
        """Test git sim."""

        gs = GitSim(argparse.Namespace())

        self.assertEqual(1, 1)


if __name__ == "__main__":
    unittest.main()
