# Source Adapters

One folder per source lane. Every future adapter follows the same simple flow:

```text
acquire → save original → parse → resolve KMX → source blocks → categories → Evidence
```

Rules are built from approved Evidence, not independently inside source adapters.
