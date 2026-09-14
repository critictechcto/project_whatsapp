# Use as ``lookup_value_regex`` on viewsets so detail routes never swallow sibling paths
# such as ``invitations/accept/``.
UUID_LOOKUP_REGEX = "[0-9a-fA-F-]{36}"
