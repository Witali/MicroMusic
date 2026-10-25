"""Check derived output names before an encoder can overwrite its inputs."""
from pathlib import Path


def _identity(path):
    try:
        info = path.stat()
    except FileNotFoundError:
        return None
    return (info.st_dev, info.st_ino) if info.st_ino else None


def protect_outputs(inputs, outputs, replace=None):
    """Allow explicit in-place codec output, never an implicit sidecar alias.

    Resolve symlinks and compare existing file identities for hard links.
    Multiple derived outputs must also name different files.
    """
    sources = [(Path(p).resolve(), None) for p in inputs]
    sources = [(p, _identity(p)) for p, _ in sources]
    targets = [Path(p).resolve() for p in outputs]
    replacement = tuple(Path(p).resolve() for p in replace) if replace else None
    paths, identities = set(), set()
    for target in targets:
        identity = _identity(target)
        if target in paths or (identity is not None and identity in identities):
            raise ValueError('Generated output paths collide: ' + str(target))
        paths.add(target)
        if identity is not None:
            identities.add(identity)
        for source, original_id in sources:
            if target == source or (identity is not None and identity == original_id):
                if replacement == (source, target) and source == target:
                    continue
                raise ValueError('Generated output would overwrite an input: ' + str(source))
