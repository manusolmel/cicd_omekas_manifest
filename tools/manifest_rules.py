# Rules-only module

# Manifest identity 
EXPECTED_API_VERSION = "libnamic.omk/v1"
EXPECTED_KIND = "OmekaSProject"

# Required top-level paths (presence only; types validated separately).
REQUIRED_PATHS = [
    ("apiVersion",),
    ("kind",),

    ("project",),
    ("project", "name"),
    ("project", "description"),
    ("project", "image"),
    ("project", "image", "name"),

    ("base",),
    ("base", "image"),
    ("base", "tag"),
    ("base", "digest"),
    
    ("extensions",),
    ("extensions", "modules"),
    ("extensions", "themes"),
]

# Exact values for specific fields.
EXACT_VALUES = {
    ("apiVersion",): EXPECTED_API_VERSION,
    ("kind",): EXPECTED_KIND,
}

# Required keys inside each list item (modules/themes).
LIST_ITEM_REQUIRED = {
    ("extensions", "modules"): [
        ("name",),
        ("source",),
        ("source", "type"),
    ],
    ("extensions", "themes"): [
        ("name",),
        ("source",),
        ("source", "type"),
    ],
}

# Minimal type checks for known fields.
EXPECTED_TYPES = {
    ("apiVersion",): str,
    ("kind",): str,
    ("project",): dict,
    ("project", "name"): str,
    ("project", "description"): str,
    ("project", "image"): dict,
    ("project", "image", "name"): str,
    ("base",): dict,
    ("base", "image"): str,
    ("base", "tag"): str,
    ("base", "digest"): str,
    ("extensions",): dict,
    ("extensions", "modules"): list,
    ("extensions", "themes"): list,
    # build is optional; types are validated only if the paths exist.
    ("build",): dict,
    ("build", "enable_tests"): bool,
    ("build", "target_tags"): list,
}

# Supported extension source types.
SUPPORTED_SOURCE_TYPES = {
    "git",
    "release_zip",
    "catalog",
    "omeka-s-cli",  # optional but supported
}

# Required keys inside "source" depending on source.type.
SOURCE_TYPE_REQUIRED = {
    "git": [
        ("repo",),
        ("ref",),
    ],
    "release_zip": [
        ("repo",),
        ("version",),
        ("asset",),
        ("sha256",),
    ],
    "catalog": [
        ("version",),
        ("sha256",),
    ],
    "omeka-s-cli": [
        ("version",),
        ("sha256",),
    ],
}

# Expected types for the required keys inside "source" by source.type.
SOURCE_TYPE_REQUIRED_TYPES = {
    "git": {
        ("repo",): str,
        ("ref",): str,
    },
    "release_zip": {
        ("repo",): str,
        ("version",): str,
        ("asset",): str,
        ("sha256",): str,
    },
    "catalog": {
        ("version",): str,
        ("sha256",): str,
    },
    "omeka-s-cli": {
        ("version",): str,
        ("sha256",): str,
    },
}

# Optional: element types for known lists.
LIST_ELEMENT_TYPES = {
    ("build", "target_tags"): str,  # each entry must be a string tag
}
