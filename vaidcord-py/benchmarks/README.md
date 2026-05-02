# Benchmarks

Small reproducible benchmarks for hot paths that are hard to protect with unit
tests alone.

Run the router hot-path benchmark from `vaidcord-py`:

```bash
python benchmarks/router_hot_path.py --events 10000 --filters 10 --middlewares 4
```

For quick CI or local smoke checks:

```bash
python benchmarks/router_hot_path.py --events 100 --filters 3 --middlewares 1
```

