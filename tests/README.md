# Testing
---

Testing is done with pytest. The focus for now is on end-to-end tests, which show that the overall project is working as it should.

## Running tests

The following instructions will let you run tests as soon as you clone the repository:

```sh
$ git clone https://github.com/initialcommit-com/git-sim.git
$ cd git-sim
$ python3 -m venv .venv
$ source venv/bin/activate
(.venv)$ pip install -e .
(.venv)$ pip install pytest
(.venv)$ pytest -s
```

Including the `-s` flag tells pytest to include diagnostic information in the test output. This will show you where the test data is being written:

```sh
(.venv)$ pytest -s
===== test session starts ==========================================
platform darwin -- Python 3.11.2, pytest-7.3.2, pluggy-1.0.0
rootdir: /Users/.../git-sim
collected 3 items

tests/e2e_tests/test_core_commands.py 

Temp repo directory:
  /private/var/folders/.../pytest-108/sample_repo0

...

===== 3 passed in 6.58s ============================================
```

## Helpful pytest notes

- `pytest -x`: Stop after the first test fails

## Adding more tests

To add another test:

- Work in `tests/e2e_tests/test_core_commands.py.
- Duplicate one of the existing test functions.
- Replace the value of `raw_cmd` with the command you want to test.
- Run the test suite once with `pytest -sx`. The test should fail, but it will generate the output you need to finish the process.
- Look in the "Temp repo directory" specified at the start of the test output.
    - Find the `git-sim_media/` directory there, and find the output file that was generated for the test you just wrote.
    - Open that file, and make sure it's correct.
    - If it is, copy that file into `tests/e2e_tests/reference_files/`, with an appropriate name.
    - Update your new test function so that `fp_reference` points to this new reference file.
- Run the test suite again, and your test should pass.
- You will need to repeat this process once on macOS or Linux, and once on Windows.

## Cross-platform issues

There are two cross-platform issues to be aware of.

### Inconsistent png and jpg output

When git-sim generates a jpg or png file, that file can be slightly different on different systems. Files can be slightly different depending on the architecture, and which system libraries are installed. Even Intel and Apple-silicon Macs can end up generating non-identical image files.

These issues are mostly addressed by checking that image files are similar within a given threshold, rather than identical.

### Inconsistent Windows and macOS output

The differences across OSes is even greater. I believe this may have something to do with which fonts are available on each system.

This is dealt with by having Windows-specific reference files.