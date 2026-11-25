## Use a cryptographic RNG for random strings

`generate_random_string` in `conduit/apps/core/utils.py` uses `random.choice`. Switch it to the `secrets`
module, keeping the signature and the defaults, and run the project's test suite to confirm nothing breaks.
