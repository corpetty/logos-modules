Icons for externally-published modules.

`gen_site.py`'s `find_icon()` looks for a module's `icon` file in the
checked-out submodules first, then here. Every module in this catalog is
built from a submodule, so this directory is empty — it exists for
modules listed in `external-modules.txt`, which have no submodule to read
an icon from. Drop the icon in under its `metadata.json` basename.
