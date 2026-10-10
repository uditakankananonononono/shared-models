# ProductConfig repr exclusion (CFG1)

Base `be24fc11543847aa3e2c2c9bb030df7ab5cf29b9` (peer main, verified with `git ls-remote origin refs/heads/main` at 14:12 IST). Authored, not run (PREP-NORUN). Application approved by the peer for config.py for this unit only (relayed by main at 14:12 IST).

## Change
- `instinct_models/config.py`: `jev_api_key` and `extra` are `field(..., repr=False)`. Storage, defaults, `load_config` and field order are unchanged. Per the Python 3.12 dataclasses documentation (https://docs.python.org/3.12/library/dataclasses.html, `field` repr parameter) a field with `repr=False` is left out of the generated `__repr__`; `str()` falls back to `__repr__`.
- `README.md` (Config section): the unsupported "never stored" sentence is replaced. New text: HF_TOKEN comes from the environment; the Jev key from the environment or the optional config file; keys are held in runtime memory; the repr leaves out `jev_api_key` and `extra`; `dataclasses.asdict` and `dataclasses.replace` still carry the values.
- `tests/test_config_repr.py`: 7 tests (authored, not run).

## Unsupported assertion removed (READ)
README.md:52 said the keys are "never stored". Source: `config.py` stores `jev_api_key` (field, and `load_config` for env and file) and `JevEval` stores `self.api_key` (providers.py:560). The new wording makes no claim about disk. The package's write paths (dataset output, training registry, provenance script) do not serialize `ProductConfig` (READ by grep: no asdict/pickle of it), but this unit does not assert a no-disk-write guarantee.

## Excluded / not claimed
`dataclasses.asdict`, `dataclasses.replace` and attribute access still expose the values; the generated repr is the only surface changed. No security proof is claimed. Provider objects are plain classes (providers.py:82 `class Provider(ABC)`), so their default object repr does not list attributes; that is not asserted as protection either.

## Not run
No tests, no import of the product.
