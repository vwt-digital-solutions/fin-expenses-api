import re
from collections import Iterable

from six import string_types
from flask import request

RegexObject = type(re.compile(''))
DEFAULT_OPTIONS = dict(resources=[{'pattern': r'/.*', 'action': 'no-store'}])


def parse_resources(resources):
    if isinstance(resources, dict):
        # To make the API more consistent with the decorator, allow a
        # resource of '*', which is not actually a valid regexp.
        resources = [(re_fix(k), v) for k, v in resources.items()]

        # Sort by regex length to provide consistency of matching and
        # to provide a proxy for specificity of match. E.G. longer
        # regular expressions are tried first.
        def pattern_length(pair):
            maybe_regex, _ = pair
            return len(get_regexp_pattern(maybe_regex))

        return sorted(resources,
                      key=pattern_length,
                      reverse=True)

    elif isinstance(resources, string_types):
        return [(re_fix(resources), {})]

    elif isinstance(resources, Iterable):
        return [(re_fix(r), {}) for r in resources]

    # Type of compiled regex is not part of the public API. Test for this
    # at runtime.
    elif isinstance(resources, RegexObject):
        return [(re_fix(resources), {})]

    else:
        raise ValueError("Unexpected value for resources argument.")


def get_regexp_pattern(regexp):
    """
    Helper that returns regexp pattern from given value.

    :param regexp: regular expression to stringify
    :type regexp: _sre.SRE_Pattern or str
    :returns: string representation of given regexp pattern
    :rtype: str
    """
    try:
        return regexp.pattern
    except AttributeError:
        return str(regexp)


def re_fix(reg):
    """
        Replace the invalid regex r'*' with the valid, wildcard regex r'/.*' to
        enable the CacheControl app extension to have a more user friendly api.
    """
    return r'.*' if reg == r'*' else reg


def try_match_any(inst, patterns):
    return any(try_match(inst, pattern) for pattern in patterns)


def try_match(request_origin, maybe_regex):
    """Safely attempts to match a pattern or string to a request origin."""
    if isinstance(maybe_regex, RegexObject):
        return re.match(maybe_regex, request_origin)
    elif probably_regex(maybe_regex):
        return re.match(maybe_regex, request_origin, flags=re.IGNORECASE)
    else:
        try:
            return request_origin.lower() == maybe_regex.lower()
        except AttributeError:
            return request_origin == maybe_regex


def probably_regex(maybe_regex):
    if isinstance(maybe_regex, RegexObject):
        return True

    common_regex_chars = ['*', '\\', ']', '?', '$', '^', '[', ']', '(', ')']
    # Use common characters used in regular expressions as a proxy
    # for if this string is in fact a regex.
    return any((c in maybe_regex for c in common_regex_chars))
