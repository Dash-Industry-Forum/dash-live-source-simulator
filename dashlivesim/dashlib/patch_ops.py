# Generates nodes conformant with DASH restricted form of https://tools.ietf.org/html/rfc5261
from xml.etree import ElementTree
PATCH_OP_NAMESPACE = "{urn:ietf:params:xml:schema:patch-ops}"

def add_ns(element):
    parts = element.split('/')
    return "/".join([PATCH_OP_NAMESPACE + e for e in parts])

def insert_replace_op(target, selector):
    replace_elem = ElementTree.Element(add_ns('replace'))
    replace_elem.tail = "\n"
    replace_elem.set('sel', selector)
    target.append(replace_elem)
    return replace_elem

def insert_add_op(target, selector, pos):
    add_elem = ElementTree.Element(add_ns('add'))
    add_elem.tail = "\n"
    add_elem.set('sel', selector)
    add_elem.set('pos', pos)
    target.append(add_elem)
    return add_elem

def insert_remove_op(target, selector):
    remove_elem = ElementTree.Element(add_ns('remove'))
    remove_elem.tail = "\n"
    remove_elem.set('sel', selector)
    # ws attribute omitted as it is not critical to MPDs
    target.append(remove_elem)
    return remove_elem