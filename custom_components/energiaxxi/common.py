import re


def slugify(value):
    return re.sub(r'[^a-z0-9_]+', '_', value.lower()).strip('_')
