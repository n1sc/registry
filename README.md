# ntsc registry

The package index behind `ntsc pkg`. The compiled index is served at
`https://ntsc.yasakei.dev/v1/registry`, and `ntsc pkg install` reads it
directly.

Adding a package is a pull request that adds one file.

## Adding a package

1. Publish your module as a git repository and tag releases with semantic
   versions (`v1.0.0`, `v1.1.0`, …).
2. Add `packages/<name>.toml`:

   ```toml
   [package]
   name = "json"
   description = "JSON parsing and encoding"
   repo = "https://github.com/you/ntsc-json"
   license = "MIT"
   keywords = ["json", "serialization"]
   ```

   `name` must equal the file name and use lowercase letters, digits, `.`,
   `_` and `-`.

3. Check it locally:

   ```bash
   python3 scripts/build_index.py --validate-only
   ```

4. Open a pull request. CI validates the file; once it is merged, the index is
   rebuilt and the site picks it up within five minutes.

Versions are discovered from the repository's tags, so there is no second
place to update when you release. A repository that CI cannot reach can list
them explicitly:

```toml
[package]
name = "json"
description = "JSON parsing and encoding"
repo = "https://example.com/json.git"
license = "MIT"
keywords = ["json"]
versions = ["1.0.0", "1.1.0"]
```

## Requirements

A package must:

- live in a public git repository reachable over `https://`, `http://`,
  `ssh://` or `git@`,
- carry a `neutron.toml` at the repository root with a `[package]` table,
- export its API from `lib.nt` or `src/lib.nt` at that root,
- tag releases with semantic versions.

The compiler vendors a package into `.ntsc/<name>/` inside the consumer
project, so imports are written with the package name:

```ntsc
use json
```

## How the index is built

`scripts/build_index.py` reads every `packages/*.toml`, resolves tags with
`git ls-remote`, and writes `index.json`:

```json
{
  "version": 1,
  "packages": [
    {
      "name": "json",
      "description": "JSON parsing and encoding",
      "repo": "https://github.com/you/ntsc-json",
      "license": "MIT",
      "keywords": ["json", "serialization"],
      "versions": ["1.0.0", "1.1.0"]
    }
  ]
}
```

`.github/workflows/index.yml` regenerates and commits it on every push to
`main`, and `.github/workflows/validate.yml` runs the schema checks on pull
requests.
